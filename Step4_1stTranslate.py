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
    SubtitleSegment, parse_sbv_file, save_sbv_file, 
    get_output_folder, replace_chinese
)

#CONFIG_FILENAME = "configuration.txt"
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
PART_EN_SUFFIX = "-Step3.sbv"  # 英文字幕文件后缀（来自Step3的输出）
PART_CH1_SUFFIX = "-Step4.sbv"  # 第一轮中文字幕文件后缀
PART_CH1_NO_PUNCTUATION_SUFFIX = "-Step4-english-chinese.sbv"  # 去掉标点符号的中文字幕文件后缀
INPUT_PREFIX = ""  # 输入文件前缀（来自Step3）
OUTPUT_PREFIX = ""  # 输出文件前缀

# 翻译配置
INCLUDE_ENGLISH = True  # 是否包含英文字幕
DEFAULT_MODEL = "deepseek"  # 默认使用的模型

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
        self.part_en_suffix = PART_EN_SUFFIX
        self.part_ch1_suffix = PART_CH1_SUFFIX
        self.part_ch1_no_punctuation_suffix = PART_CH1_NO_PUNCTUATION_SUFFIX
        self.input_prefix = INPUT_PREFIX
        self.output_prefix = OUTPUT_PREFIX
        
        self.model_config = model_config    
        self.client = self._init_client()

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        # get the api key from the MODEL_CONFIGS
        model_settings = MODEL_CONFIGS[self.model_config]
        api_key = model_settings.get("api_key")
        if not api_key:
            raise ValueError(f"配置文件缺少 '{self.model_config}-key' 配置项")
            
        if model_settings["base_url"]:
            return OpenAI(
                api_key=api_key,
                base_url=model_settings["base_url"]
            )
        return OpenAI(api_key=api_key)

    def _get_translation_prompt(self) -> str:
        """获取翻译提示"""
        Prompt = """请将下面的基督教会的讲道信息翻译为简体中文，完全忠于原意，使用基督教会用语，以及口语化中文。

翻译规则：
1. 保持所有的时间戳，时间戳数量必须与原文完全相同
2. 每个时间戳下的中文内容必须对应原文相同时间戳下的内容
3. 圣经经文使用中文和合本圣经 http://mobile.chinesebibleonline.com/bible，圣经经文不可以意译。遇到圣经书名，请加上中文书名号《》。
4. Saddleback Church或者Saddleback都翻译为马鞍峰教会
5. 使用中文通顺的习惯表达及基督教会用语
6. 上帝翻译为神；神的代名词使用祢/祂，否则用你/他（她）。
7. Dream Now→'筑梦当下', campus→分堂, group→小组, 用祷告不用祈祷, 用神不用上帝
8. 所有引号统一使用英文双引号"
9. 圣经经节表达用5:1或5:1-5格式

输出格式要求：
- 严格按照以下格式输出，不要添加任何额外的说明或标记
- 每个时间戳下先输出英文原文，再输出中文翻译
- 确保时间戳数量与原文完全一致

格式示例：
00:00:00.000,00:00:05.000
英文:This is English text
中文:这是中文翻译

00:00:05.000,00:00:10.000
英文:Another English text
中文:另一个中文翻译

重要：请确保输出的时间戳数量与输入的时间戳数量完全一致，不要遗漏任何时间戳。"""
        return Prompt

    def _translate_segments(self, segments: List[SubtitleSegment]) -> Optional[List[SubtitleSegment]]:
        """翻译字幕片段"""
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
            translated_segments = []
            current_times = None
            current_text = []
            
            for line in translated_text.split('\n'):
                line = line.strip()
                if not line:
                    if current_times and current_text:
                        start_time, end_time = current_times
                        translated_segments.append(SubtitleSegment(
                            start_time=start_time,
                            end_time=end_time,
                            text='\n'.join(current_text)
                        ))
                        current_times = None
                        current_text = []
                    continue
                
                # 识别时间戳行（包含逗号且冒号数量为4）
                if ',' in line and line.count(':') == 4:
                    start_time, end_time = line.split(',')
                    current_times = (start_time, end_time)
                # 识别中文翻译内容（以"中文:"开头）
                elif current_times:
                    current_text.append(line)
            
            # 处理最后一个片段
            if current_times and current_text:
                start_time, end_time = current_times
                translated_segments.append(SubtitleSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text='\n'.join(current_text)
                ))
            
            # 验证片段数量
            if len(translated_segments) != len(segments):
                print(f"⚠️  警告：翻译后的片段数量({len(translated_segments)})与原文片段数量({len(segments)})不一致")
                print(f"这可能是由于AI翻译格式问题导致的，建议检查翻译质量")
            
            return translated_segments
            
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

    def _process_single_part(self, part_name: str) -> bool:
        """处理单个Part"""
        try:
            # 将part1转换为Part1格式
            part_name_capitalized = part_name.capitalize()
            en_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_en_suffix}")
            ch_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch1_suffix}")
            ch_no_punctuation_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch1_no_punctuation_suffix}")

            print(f"\n处理 {part_name}")
            print(f"英文文件: {en_file}")
            print(f"中文文件: {ch_file}")
            print(f"中文无标点文件: {ch_no_punctuation_file}")
            
            # 读取英文字幕
            en_segments = parse_sbv_file(en_file)
            print(f"读取到 {len(en_segments)} 个英文字幕片段")
            
            # 翻译字幕
            ch_segments = self._translate_segments(en_segments)
            if not ch_segments:
                raise Exception("翻译失败")
            print(f"翻译得到 {len(ch_segments)} 个中文字幕片段")
           
            # 保存中文字幕（原版）
            save_sbv_file(ch_segments, ch_file)
            print(f"已保存中文字幕: {ch_file}")
            
            # 保存中文字幕（去掉标点符号版本）
            ch_no_punctuation_segments = []
            for segment in ch_segments:
                new_segment = SubtitleSegment(
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text=replace_chinese(segment.text)
                )
                ch_no_punctuation_segments.append(new_segment)
            
            save_sbv_file(ch_no_punctuation_segments, ch_no_punctuation_file)
            print(f"已保存中文无标点字幕: {ch_no_punctuation_file}")
            
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
            print(f"✅ Step4 处理完成！")
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