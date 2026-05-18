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
PART_CH1_MEANING_ONLY_SUFFIX = "-Step5-meaning_only.sbv"  # 输入文件后缀（意译版本）
PART_CH1_CHINESE_ONLY_SUFFIX = "-Step5-chinese_only.sbv"  # 输入文件后缀（直译版本）
PART_CH2_MEANING_ONLY_SUFFIX = "-Step6-meaning_only.sbv"  # 输出文件后缀（意译版本）
PART_CH2_CHINESE_ONLY_SUFFIX = "-Step6-chinese_only.sbv"  # 输出文件后缀（直译版本）
INPUT_PREFIX = ""  # 输入文件前缀
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
        self.part_ch1_meaning_only_suffix = PART_CH1_MEANING_ONLY_SUFFIX
        self.part_ch1_chinese_only_suffix = PART_CH1_CHINESE_ONLY_SUFFIX
        self.part_ch2_meaning_only_suffix = PART_CH2_MEANING_ONLY_SUFFIX
        self.part_ch2_chinese_only_suffix = PART_CH2_CHINESE_ONLY_SUFFIX
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
        """获取翻译提示 - 简化版本"""
        Prompt = """请优化以下基督教讲道字幕的格式，使其更易于观众阅读。

【任务】
将字幕按时长和字数优化，确保观众阅读舒适。

【内容完整性】
- 输入的每段内容在输出中只出现一次
- 所有输入内容都必须出现在输出中，不可遗漏
- 只输出原始内容，不添加任何说明、注释、标记或括号内的解释

【时长规则】
- 每个屏幕时长应在2-6秒之间
- 超过6秒：按字数比例分屏
- 不足2秒：与相邻屏幕合并

【字数规则】
- 每屏约25个中文字
- 15-30字时分为两行
- 10字以下保持一行

【时间戳规则】
- 未分屏的屏幕：保持原时间戳不变
- 分屏时：首屏开始=原开始，末屏结束=原结束，中间按字数比例分配

【过渡句处理】
- 短过渡句（如"他说"、"所以 请注意"、"在第X节 他说："）应与前后内容合并

【示例1 - 分行】
原文（时长5.4秒，在2-6秒内，只需分行）：
00:02:32.080,00:02:37.510
医院肯定不会让新手父母独自带孩子回家吧？但他們真的这么做了！

处理后（时间戳不变，分为两行）：
00:02:32.080,00:02:37.510
医院肯定不会让新手父母独自带孩子回家吧？
但他們真的这么做了！

【示例2 - 分屏】
原文（时长6.6秒，超过6秒需分屏）：
00:04:31.840,00:04:38.430
现在很多父母整天忙着教养儿女 却从没停下来思想：我教养的终极目标是什么？我究竟为何而教养？

处理后（分为两屏，每屏约3.3秒）：
00:04:31.840,00:04:35.135
现在很多父母整天忙着教养儿女
却从没停下来思想：

00:04:35.185,00:04:38.430
我教养的终极目标是什么？
我究竟为何而教养？

【示例3 - 合并】
原文（第二屏只有1.5秒，不足2秒需合并）：
00:05:10.000,00:05:14.000
所以 请注意他所说的

00:05:14.050,00:05:15.550
他说

处理后（合并为一屏，5.5秒）：
00:05:10.000,00:05:15.550
所以 请注意他所说的 他说

【示例4 - 过渡句合并】
原文（第一屏是1.5秒的过渡句）：
00:21:48.000,00:21:49.500
所以 请注意他说的

00:21:49.550,00:21:54.000
如果你脱去说谎 现在就必须穿上真理

处理后（过渡句与后面内容合并，6秒）：
00:21:48.000,00:21:54.000
所以 请注意他说的 如果你脱去说谎
现在就必须穿上真理

【输出格式】
- 严格按照输入的时间戳格式输出
- 不要添加任何额外的说明、注释或标记
- 不要创造新内容，只处理输入中已有的文字
"""
        
        return Prompt  

    def _extract_meaning_only(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """从包含直译+意译的字幕中提取只意译的部分"""
        meaning_only_segments = []
        
        for segment in segments:
            lines = segment.text.split('\n')
            meaning_lines = []
            
            for line in lines:
                line = line.strip()
                # 如果行以"意译:"开头，提取意译内容
                if line.startswith('意译:'):
                    meaning_content = line[3:].strip()  # 去掉"意译:"前缀
                    if meaning_content:
                        meaning_lines.append(meaning_content)
                # 如果行不以任何前缀开头，且前面有意译行，则认为是意译的继续
                elif meaning_lines and not line.startswith(('中文:', '英文:')):
                    meaning_lines.append(line)
            
            if meaning_lines:
                # 创建新的字幕片段，只包含意译内容
                meaning_only_segments.append(SubtitleSegment(
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    text='\n'.join(meaning_lines)
                ))
            else:
                # 如果没有找到意译内容，保留原片段
                meaning_only_segments.append(segment)
        
        return meaning_only_segments

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
                
                if ',' in line and line.count(':') == 4:
                    start_time, end_time = line.split(',')
                    current_times = (start_time, end_time)
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

    def _process_single_part(self, part_name: str, input_suffix: str, output_suffix: str, translation_type_name: str) -> bool:
        """处理单个Part"""
        try:
            # 将part1转换为Part1格式
            part_name_capitalized = part_name.capitalize()
            input_file = os.path.join(self.output_folder, f"{part_name_capitalized}{input_suffix}")
            output_file = os.path.join(self.output_folder, f"{part_name_capitalized}{output_suffix}")
            
            print(f"\n处理 {part_name}")
            print(f"输入文件: {input_file}")
            
            if not os.path.exists(input_file):
                print(f"        未找到输入文件: {input_file}")
                return False
            
            input_segments = parse_sbv_file(input_file)
            print(f"读取到 {len(input_segments)} 个字幕片段")
            
            # 进行分屏处理
            output_segments = self._translate_segments(input_segments)
            if not output_segments:
                raise Exception("分屏处理失败")
            
            print(f"分屏处理得到 {len(output_segments)} 个字幕片段")
            
            # 保存处理后的版本
            for segment in output_segments:
                segment.text = replace_chinese(segment.text)
            save_sbv_file(output_segments, output_file)
            print(f"✓ 已保存{translation_type_name}版本")
            
            return True
            
        except Exception as e:
            print(f"处理 {part_name} 时出错: {str(e)}")
            traceback.print_exc()
            return False

    def process(self) -> bool:
        """主处理函数（并行处理）"""
        try:
            # 在process函数中询问用户要处理的翻译类型
            translation_type = get_user_choice()
            
            # 根据翻译类型选择输入和输出文件后缀
            if translation_type == "meaning_only":
                input_suffix = self.part_ch1_meaning_only_suffix
                output_suffix = self.part_ch2_meaning_only_suffix
                translation_type_name = "意译"
            elif translation_type == "chinese_only":
                input_suffix = self.part_ch1_chinese_only_suffix
                output_suffix = self.part_ch2_chinese_only_suffix
                translation_type_name = "直译"
            else:
                raise ValueError(f"不支持的翻译类型: {translation_type}")
            
            print(f"\n🔄 开始处理 {len(self.parts)} 个Parts...")
            
            # 🚀 并行处理Parts
            print(f"⚡ 使用并行处理（最多 {MAX_PARALLEL_PARTS} 个并发）...\n")
            
            start_time = time.time()
            success_count = 0
            
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PARTS) as executor:
                future_to_part = {executor.submit(self._process_single_part, part, input_suffix, output_suffix, translation_type_name): part for part in self.parts}
                
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
            print(f"✅ Step6 处理完成！")
            print(f"成功: {success_count}/{len(self.parts)} Parts")
            print(f"总耗时: {elapsed:.1f}秒")
            print(f"{'='*60}\n")
            
            return success_count > 0
            
        except Exception as e:
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return False

def get_user_choice():
    """获取用户选择"""
    while True:
        print("\n请选择要处理的翻译类型：")
        print("1. 意译版本")
        print("2. 直译版本")
        print("0. 退出")
        
        choice = input("请输入选择 (1/2/0): ").strip()
        
        if choice == "0":
            raise ValueError("用户选择退出")
        elif choice == "1":
            return "meaning_only"
        elif choice == "2":
            return "chinese_only"
        else:
            print("请输入有效的选择 (1/2/0)")

def main():
    try:
        # 获取用户选择
        translation_type = get_user_choice()
        
        # 使用默认的parts（由main.py传入）
        parts = [f"part{i}" for i in range(1, 11)]
        
        output_folder = get_output_folder(DEFAULT_OUTPUT_FOLDER)
        if not output_folder:
            raise ValueError("配置文件中缺少'outputfolder'设置")
            
        processor = SubtitleTranslator(parts, output_folder, translation_type)
        result = processor.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()