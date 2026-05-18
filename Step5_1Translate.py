######################################################################
#  COPYRIGHT 2023-24 
#  Function：翻译为中文
######################################################################
import os
import traceback
import time
from typing import List, Dict, Optional
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from common_utils import (
    SubtitleSegment, parse_sbv_file, replace_chinese, save_sbv_file, 
    get_output_folder
)

CONFIG_FILENAME = "configuration.txt"
DEFAULT_OUTPUT_FOLDER = "DataFiles"  # Set this to a specific folder name if you want to override the date-based folder
MODEL="deepseek"

# 性能优化配置
MAX_PARALLEL_PARTS = 3  # 并行处理的最大Part数量（避免超过API限制）

# 模型配置
MODEL_CONFIGS = {
    "deepseek": {
        "model": "deepseek-reasoner",
        "api_key": "sk-xxxx",  # Redacted private DeepSeek API key -> replaced with 'xxxx' for security
        "base_url": "https://api.deepseek.com"
    },
    "openai": {
        "model": "gpt-3.5-turbo",
        "api_key": None,  # 从配置文件读取
        "base_url": None
    },
    "o3-mini": {
        "model": "o3-mini",
        "api_key": None,  # 从配置文件读取
        "base_url": None
    }
}

# 文件名配置
PART_CH1_SUFFIX = "-Step4.sbv"  # 第一轮中文字幕文件后缀（来自Step4的输出）
PART_CH2_CHINESE_MEANING_SUFFIX = "-Step5-chinese_meaning.sbv"  # 第二轮中文字幕文件后缀（直译+意译）
PART_CH2_MEANING_ONLY_SUFFIX = "-Step5-meaning_only.sbv"  # 第二轮中文字幕文件后缀（只意译）
PART_CH2_CHINESE_ONLY_SUFFIX = "-Step5-chinese_only.sbv"  # 第二轮中文字幕文件后缀（只直译）
PART_CH2_ALL_SUFFIX = "-Step5-all.sbv"  # 第二轮中文字幕文件后缀（英文+中文+意译）
INPUT_PREFIX = ""  # 输入文件前缀（来自Step4）
OUTPUT_PREFIX = ""  # 输出文件前缀

# 翻译配置
INCLUDE_ENGLISH = True  # 是否包含英文字幕
DEFAULT_MODEL = "deepseek"  # 默认使用的模型

# 输出版本配置
VERSION_CHINESE_MEANING = "chinese_meaning"  # 保留中文和意译
VERSION_MEANING_ONLY = "meaning_only"  # 只保留意译
VERSION_CHINESE_ONLY = "chinese_only"  # 只保留中文（直译）
VERSION_ALL = "all"  # 保留英文、中文和意译

class SubtitleTranslator:
    def __init__(self, parts: List[str], output_folder: str, model_config: str = DEFAULT_MODEL):
        self.output_folder = output_folder
        self.include_english = INCLUDE_ENGLISH
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")
        
        # 验证并存储parts列表
        self.parts = []
        for part in parts:
            if not part.lower().startswith('part'):
                raise ValueError(f"无效的Part名称: {part}，必须以'part'开头")
            if not part[4:].isdigit():
                raise ValueError(f"无效的Part名称: {part}，'part'后必须是数字")
            if not (1 <= int(part[4:]) <= 100):
                raise ValueError(f"无效的Part名称: {part}，数字必须在1-100范围内")
            self.parts.append(part)
        
        # 按编号排序parts
        self.parts.sort(key=lambda x: int(x.lower().replace('part', '')))
        
        if not self.parts:
            raise ValueError("未提供任何有效的Part")
            
        print(f"找到以下Parts: {', '.join(self.parts)}")
        
        # 使用常量定义的文件名设置
        self.part_ch1_suffix = PART_CH1_SUFFIX
        self.part_ch2_chinese_meaning_suffix = PART_CH2_CHINESE_MEANING_SUFFIX
        self.part_ch2_meaning_only_suffix = PART_CH2_MEANING_ONLY_SUFFIX
        self.part_ch2_chinese_only_suffix = PART_CH2_CHINESE_ONLY_SUFFIX
        self.part_ch2_all_suffix = PART_CH2_ALL_SUFFIX
        self.input_prefix = INPUT_PREFIX
        self.output_prefix = OUTPUT_PREFIX
        
        self.model_config = model_config
        self.client = self._init_client()

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        # get the api key from the MODEL_CONFIGS
        model_settings = MODEL_CONFIGS[self.model_config]
        api_key = model_settings.get("api_key")

        if model_settings["base_url"]:
            return OpenAI(
                api_key=model_settings["api_key"],
                base_url=model_settings["base_url"]
            )
        return OpenAI(api_key=model_settings["api_key"])

    def _get_translation_prompt(self) -> str:
        """获取翻译提示"""
        Prompt = """请将下面的基督教会的讲道'中文'翻译加以改进,提高翻译质量，使用口语化中文，以及基督教会用语重写中文翻译。

翻译规则：
1. 保持所有的时间戳，时间戳数量必须与原文完全相同
2. 圣经经文使用中文和合本圣经 http://mobile.chinesebibleonline.com/bible，圣经经文不可以意译。遇到圣经书名，请加上中文书名号《》。
3. Saddleback Church或者Saddleback都翻译为马鞍峰教会
4. 使用中文通顺的习惯表达及基督教会用语
5. 上帝翻译为神；神的代名词使用祢/祂，否则用你/他（她）。
6. Dream Now→'筑梦当下', campus→分堂, group→小组, 用祷告不用祈祷, 用神不用上帝
7. 所有引号统一使用英文双引号"
8. 圣经经节表达用5:1或5:1-5格式  
9. 如果可能，请使用非常接近的中文成语。
10. 在每个时间戳下，先输出英文原文，再输出原有的中文翻译，最后输出改进后的'意译'中文翻译

输出格式要求：
- 严格按照以下格式输出，不要添加任何额外的说明或标记
- 每个时间戳下先输出英文原文，再输出中文原文, 最后输出改进后的'意译'中文翻译
- 确保时间戳数量与原文完全一致

格式示例：
00:00:00.000,00:00:05.000
英文:This is English text
中文:这是中文原文
意译:这是中文意译翻译版本

00:00:05.000,00:00:10.000
英文:Another English text
中文:另一个中文原文
意译:另一个中文意译翻译版本

重要：请确保输出的时间戳数量与输入的时间戳数量完全一致，不要遗漏任何时间戳。"""
        return Prompt

    def _translate_segments(self, segments: List[SubtitleSegment]) -> Optional[Dict[str, List[SubtitleSegment]]]:
        """翻译字幕片段，返回两个版本的翻译结果"""
        try:
            # 构建输入文本
            input_text = ""
            for segment in segments:
                input_text += f"{segment.start_time},{segment.end_time}\n"
                input_text += f"{segment.text}\n\n"
            
            # 调用API进行翻译
            response = self.client.chat.completions.create(
                model=MODEL_CONFIGS[self.model_config]["model"],
                messages=[
                    {"role": "system", "content": self._get_translation_prompt()},
                    {"role": "user", "content": input_text}
                ]
            )
            
            # 解析翻译结果
            translated_text = response.choices[0].message.content
            results = {}
            
            # 为每个版本生成翻译结果
            for version in [VERSION_CHINESE_MEANING, VERSION_MEANING_ONLY, VERSION_CHINESE_ONLY, VERSION_ALL]:
                translated_segments = []
                
                # 将整个翻译结果按空行分割成各个片段
                segments_text = translated_text.split('\n\n')
                
                for i, segment_text in enumerate(segments_text):
                    if not segment_text.strip():
                        continue
                        
                    # 使用_parse_single_segment来解析每个片段
                    if i < len(segments):
                        original_segment = segments[i]
                        translated_segment = self._parse_single_segment(
                            segment_text, 
                            original_segment.start_time, 
                            original_segment.end_time,
                            version
                        )
                        
                        if translated_segment:
                            translated_segments.append(translated_segment)
                        else:
                            print(f"⚠️  警告：片段 {i+1} 翻译失败，使用原文")
                            translated_segments.append(original_segment)
                    else:
                        # 如果片段数量不匹配，尝试解析最后一个片段
                        if segments:
                            original_segment = segments[-1]
                            translated_segment = self._parse_single_segment(
                                segment_text, 
                                original_segment.start_time, 
                                original_segment.end_time,
                                version
                            )
                            if translated_segment:
                                translated_segments.append(translated_segment)
                
                # 验证片段数量
                if len(translated_segments) != len(segments):
                    print(f"⚠️  警告：{version}版本翻译后的片段数量({len(translated_segments)})与原文片段数量({len(segments)})不一致")
                    print(f"这可能是由于AI翻译格式问题导致的，建议检查翻译质量")
                    
                    # 如果翻译片段数量不足，用原文补充
                    while len(translated_segments) < len(segments):
                        missing_index = len(translated_segments)
                        translated_segments.append(segments[missing_index])
                
                results[version] = translated_segments
            
            return results
            
        except Exception as e:
            error_msg = str(e)
            if "Insufficient Balance" in error_msg or "402" in error_msg or "余额不足" in error_msg:
                print(f"❌ DeepSeek API 余额不足，无法继续翻译")
                print(f"请充值您的 DeepSeek 账户后重试")
                print(f"错误详情: {error_msg}")
            elif "Rate limit" in error_msg or "429" in error_msg or "频率限制" in error_msg:
                print(f"❌ API 调用频率过高，请稍后重试")
                print(f"错误详情: {error_msg}")
            elif "Invalid API key" in error_msg or "401" in error_msg or "无效密钥" in error_msg:
                print(f"❌ DeepSeek API 密钥无效")
                print(f"请检查您的 API 密钥是否正确")
                print(f"错误详情: {error_msg}")
            else:
                print(f"翻译时出错: {error_msg}")
                traceback.print_exc()
            return None

    def _parse_single_segment(self, translated_text: str, original_start_time: str, original_end_time: str, version: str) -> Optional[SubtitleSegment]:
        """解析单个片段的翻译结果，并根据版本过滤内容"""
        try:
            current_times = None
            english_text = []
            chinese_text = []
            meaning_text = []
            
            for line in translated_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # 识别时间戳行（包含逗号且冒号数量为4）
                if ',' in line and line.count(':') == 4:
                    start_time, end_time = line.split(',')
                    current_times = (start_time, end_time)
                # 识别英文内容
                elif current_times and line.startswith('英文:'):
                    english_text.append(line[3:].strip())
                # 识别中文内容
                elif current_times and line.startswith('中文:'):
                    chinese_text.append(line[3:].strip())
                # 识别意译内容
                elif current_times and line.startswith('意译:'):
                    meaning_text.append(line[3:].strip())
            
            # 如果解析失败，使用原始时间戳
            if not current_times:
                current_times = (original_start_time, original_end_time)
            
            # 根据版本过滤内容
            filtered_text = self._filter_content_by_version(english_text, chinese_text, meaning_text, version)
            
            if filtered_text:
                return SubtitleSegment(
                    start_time=current_times[0],
                    end_time=current_times[1],
                    text='\n'.join(filtered_text)
                )
            else:
                return None
                
        except Exception as e:
            print(f"解析单个片段时出错: {str(e)}")
            return None
    
    def _filter_content_by_version(self, english_text: List[str], chinese_text: List[str], meaning_text: List[str], version: str) -> List[str]:
        """根据版本过滤内容"""
        filtered_text = []
        
        # 根据版本收集需要的内容
        content_to_include = []
        
        if version == VERSION_CHINESE_MEANING:
            # 保留中文和意译
            if chinese_text:
                content_to_include.append(("中文", chinese_text))
            if meaning_text:
                content_to_include.append(("意译", meaning_text))
        elif version == VERSION_MEANING_ONLY:
            # 只保留意译
            if meaning_text:
                content_to_include.append(("意译", meaning_text))
        elif version == VERSION_CHINESE_ONLY:
            # 只保留中文（直译）
            if chinese_text:
                content_to_include.append(("中文", chinese_text))
        elif version == VERSION_ALL:
            # 保留英文、中文和意译
            if english_text:
                content_to_include.append(("英文", english_text))
            if chinese_text:
                content_to_include.append(("中文", chinese_text))
            if meaning_text:
                content_to_include.append(("意译", meaning_text))
        
        # 如果只有一种翻译类型，则去掉前缀
        if len(content_to_include) == 1:
            # 只有一种类型，直接添加内容，不加前缀
            _, texts = content_to_include[0]
            # 处理文本，删除引号前的中文句号
            processed_texts = [self._remove_period_before_quotes(text) for text in texts]
            filtered_text.extend(processed_texts)
        else:
            # 多种类型，添加前缀
            for prefix, texts in content_to_include:
                # 处理文本，删除引号前的中文句号
                processed_texts = [f"{prefix}:{self._remove_period_before_quotes(text)}" for text in texts]
                filtered_text.extend(processed_texts)
        
        return filtered_text

    def _remove_period_before_quotes(self, text: str) -> str:
        """删除引号前的中文句号"""
        # 使用简单的字符串替换方法
        text = text.replace('“', '"')  # 中文双引号改为英文双引号
        text = text.replace('”', '"')  # 中文双引号改为英文双引号        
        text = text.replace('‘', "'")  # 中文单引号改为英文单引号
        text = text.replace('’', "'")  # 中文单引号改为英文单引号
        text = text.replace('。"', '"')  # 中文句号 + 中文双引号
        text = text.replace("。'", "'")  # 中文句号 + 中文单引号

        return text

    def _process_single_part(self, part_name: str) -> bool:
        """处理单个Part"""
        try:
            # 将part1转换为Part1格式
            part_name_capitalized = part_name.capitalize()
            ch1_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch1_suffix}")
            ch2_chinese_meaning_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_chinese_meaning_suffix}")
            ch2_meaning_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_meaning_only_suffix}")
            ch2_chinese_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_chinese_only_suffix}")
            ch2_all_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_all_suffix}")
            
            print(f"\n处理 {part_name}")
            print(f"第一轮翻译文件: {ch1_file}")
            
            if not os.path.exists(ch1_file):
                print(f"        未找到第一轮翻译文件: {ch1_file}")
                return False
            
            ch1_segments = parse_sbv_file(ch1_file)
            print(f"读取到 {len(ch1_segments)} 个第一轮翻译字幕片段")
            
            # 翻译并生成多个版本
            translation_results = self._translate_segments(ch1_segments)
            if not translation_results:
                raise Exception("翻译失败")
            
            # 保存直译+意译版本
            ch2_chinese_meaning_segments = translation_results[VERSION_CHINESE_MEANING]
            for segment in ch2_chinese_meaning_segments:
                segment.text = replace_chinese(segment.text)
            save_sbv_file(ch2_chinese_meaning_segments, ch2_chinese_meaning_file)
            print(f"✓ 已保存直译+意译版本")
            
            # 保存只意译版本
            ch2_meaning_only_segments = translation_results[VERSION_MEANING_ONLY]
            for segment in ch2_meaning_only_segments:
                segment.text = replace_chinese(segment.text)
            save_sbv_file(ch2_meaning_only_segments, ch2_meaning_only_file)
            print(f"✓ 已保存只意译版本")
            
            # 保存只直译版本
            ch2_chinese_only_segments = translation_results[VERSION_CHINESE_ONLY]
            for segment in ch2_chinese_only_segments:
                segment.text = replace_chinese(segment.text)
            save_sbv_file(ch2_chinese_only_segments, ch2_chinese_only_file)
            print(f"✓ 已保存只直译版本")
            
            # 保存英文+中文+意译版本
            ch2_all_segments = translation_results[VERSION_ALL]
            for segment in ch2_all_segments:
                segment.text = replace_chinese(segment.text)
            save_sbv_file(ch2_all_segments, ch2_all_file)
            print(f"✓ 已保存英文+中文+意译版本")
            
            return True
            
        except Exception as e:
            print(f"处理 {part_name} 时出错: {str(e)}")
            traceback.print_exc()
            return False

    def process(self) -> bool:
        """主处理函数（并行处理）"""
        try:
            print(f"\n🔄 开始处理 {len(self.parts)} 个Parts...")
            
            # 🚀 并行处理Parts
            print(f"⚡ 使用并行处理（最多 {MAX_PARALLEL_PARTS} 个并发）...\n")
            
            start_time = time.time()
            success_count = 0
            
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PARTS) as executor:
                future_to_part = {executor.submit(self._process_single_part, part): part for part in self.parts}
                
                for future in as_completed(future_to_part):
                    part_name = future_to_part[future]
                    try:
                        success = future.result()
                        if success:
                            success_count += 1
                    except Exception as e:
                        print(f"Part {part_name} 执行失败: {e}")
            
            elapsed = time.time() - start_time
            
            print(f"\n{'='*60}")
            print(f"✅ Step5 处理完成！")
            print(f"成功: {success_count}/{len(self.parts)} Parts")
            print(f"总耗时: {elapsed:.1f}秒")
            print(f"{'='*60}\n")
            
            return success_count > 0
            
        except Exception as e:
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return False

def main():
    try:
        # Example usage with 10 parts
        parts = [f"part{i}" for i in range(1, 11)]
        output_folder = get_output_folder(DEFAULT_OUTPUT_FOLDER)
        if not output_folder:
            raise ValueError("配置文件中缺少'outputfolder'设置")
            
        processor = SubtitleTranslator(parts, output_folder)
        result = processor.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()