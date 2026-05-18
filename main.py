######################################################################
#  COPYRIGHT 2023-24 
#  Function：主程序，协调所有字幕处理步骤
######################################################################
import os
import traceback
from datetime import datetime
from typing import Dict, List
from Step1_GetVideoSubtitle import VideoProcessor
from Step2_MergeSegments import SubtitleMerger
from Step2_1_DownloadYouTubeSubtitle import YouTubeSubtitleDownloader
from Step3_SplitParts import SubtitleSplitter
from Step4_1stTranslate import SubtitleTranslator as FirstRoundTranslator
from Step5_1Translate import SubtitleTranslator as SecondRoundTranslator
from Step6_Split import SubtitleTranslator as SplitTranslator
from Step7_UploadParts import SubtitleUploader
from Step8_FinalDownloadUpload import SubtitleDownloadUploader
from Step9_MergeAllParts import PartAllMerger
from Step10_MoveOldFiles import OldFilesMover

CONFIG_FILENAME = "configuration.txt"
MODE = "local-video"  # download-google-video or local-video or local-mp3

def clean_input_for_comparison(input_str: str) -> str:
    """清理用户输入以便进行字符比较，处理中文输入模式下的英文字符识别"""
    if not input_str:
        return ""
    
    # 移除所有空白字符
    cleaned = input_str.strip().lower()
    
    # 处理全角字符转换为半角字符
    full_to_half = {
        'ｘ': 'x', 'Ｘ': 'x',
        'ｙ': 'y', 'Ｙ': 'y',
        'ｎ': 'n', 'Ｎ': 'n',
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9'
    }
    
    for full, half in full_to_half.items():
        cleaned = cleaned.replace(full, half)
    
    return cleaned

def get_youtube_url() -> str:
    """获取用户指定的YouTube URL"""
    print("\n请指定要上传字幕的YouTube视频URL：")
    print("(输入X退出当前步骤)")
    url = input().strip()
    
    # 处理中文输入模式下的英文字符识别
    url_clean = clean_input_for_comparison(url)
    if url_clean == 'x':
        raise ValueError("用户选择退出当前步骤")
    
    if not url:
        raise ValueError("必须提供YouTube视频URL")
    
    print(f"将使用指定的YouTube URL: {url}")
    return url

def get_num_parts(prompt: str, default: int = 10) -> int:
    print(f"\n{prompt} (直接回车默认为{default}):")
    print("(输入X退出当前步骤)")
    user_input = input().strip()
    
    # 处理中文输入模式下的英文字符识别
    user_input_clean = clean_input_for_comparison(user_input)
    if user_input_clean == 'x':
        raise ValueError("用户选择退出当前步骤")
    
    if not user_input:
        print(f"将使用默认分段数: {default}")
        return default
    try:
        num = int(user_input)
        if num < 1:
            raise ValueError
        print(f"将使用分段数: {num}")
        return num
    except Exception:
        print(f"输入无效，使用默认分段数: {default}")
        return default

def get_part_numbers(prompt: str, all_parts: list) -> list:
    print(f"\n{prompt} (用逗号分隔，如 1,2,3，直接回车为全部):")
    print("(输入X退出当前步骤)")
    user_input = input().strip()
    
    # 处理中文输入模式下的英文字符识别
    user_input_clean = clean_input_for_comparison(user_input)
    if user_input_clean == 'x':
        raise ValueError("用户选择退出当前步骤")
    
    if not user_input:
        print(f"将处理全部Parts: {', '.join(all_parts)}")
        return all_parts
    try:
        nums = [int(x) for x in user_input.split(',') if x.strip().isdigit()]
        selected = [f"part{n}" for n in nums if f"part{n}" in all_parts]
        print(f"将处理指定Parts: {', '.join(selected)}")
        return selected
    except Exception:
        print(f"输入无效，将处理全部Parts: {', '.join(all_parts)}")
        return all_parts

def create_parts_list(num_parts: int) -> List[str]:
    """创建指定数量的parts列表"""
    return [f"part{i}" for i in range(1, num_parts + 1)]

class SubtitleProcessor:
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")

        # 初始化各个处理器
        self.video_processor = VideoProcessor(output_folder)
        self.merger = SubtitleMerger(output_folder)
        self.splitter = None  # Will be set after user input
        self.first_translator = None
        self.second_translator = None
        self.third_translator = None
        self.uploader = None

def auto_detect_parts_list(processor):
    """自动检测已存在的分割文件并设置parts_list
    注意：每次调用都会重新检测文件，以确保检测到新添加的文件
    """
    # 总是重新检测文件，不依赖缓存，这样可以检测到新添加的文件
    # 尝试自动检测已存在的分割文件
    import glob
    
    # 检测多种可能的文件格式
    patterns = [
        "Part*-Step3.sbv",  # 原始格式
        "Part*-Step5-chinese_meaning.sbv",  # 新格式1
        "Part*-Step5-meaning_only.sbv"  # 新格式2
    ]
    
    existing_files = []
    for pattern in patterns:
        files = glob.glob(os.path.join(processor.output_folder, pattern))
        existing_files.extend(files)
    
    if existing_files:
        #print(f"找到 {len(existing_files)} 个文件:")
        #for file in existing_files:
        #    print(f"  - {file}")
        
        # 从文件名中提取part名称
        parts_list = []
        for file in existing_files:
            basename = os.path.basename(file)
            
            # 处理不同的文件格式
            if basename.startswith("Part"):
                # 提取Part后面的数字
                try:
                    # Part1-Step3.sbv -> part1
                    # Part1-Step5-chinese_meaning.sbv -> part1
                    # Part1-Step5-meaning_only.sbv -> part1
                    part_with_suffix = basename[4:]  # 去掉"Part"前缀
                    part_number = part_with_suffix.split('-')[0]  # 取第一个连字符前的部分
                    
                    if part_number.isdigit():
                        part_name = f"part{part_number}"
                        if part_name not in parts_list:
                            parts_list.append(part_name)
                            #print(f"    提取到有效part: {part_name}")
                    else:
                        print(f"    跳过无效文件名: {basename} -> 数字部分: {part_number}")
                except Exception as e:
                    print(f"    解析文件名时出错: {basename} -> {e}")
            else:
                print(f"    跳过不符合格式的文件: {basename}")
        
        if parts_list:
            parts_list.sort(key=lambda x: int(x.lower().replace('part', '')))
            processor.parts_list = parts_list
            print(f"自动检测到已存在的分割文件: {', '.join(parts_list)}")
            return parts_list
        else:
            print("所有找到的文件都不符合有效格式")
            raise Exception("未找到有效的分割文件")
    else:
        print("当前目录下没有找到任何Part文件")
        raise Exception("请先执行步骤3分割字幕")

def step1(processor):
    print("\n=== 步骤1: 处理视频并生成英文字幕 ===")
    try:
        if not processor.video_processor.process():
            raise Exception("视频处理和英文字幕生成失败")
        print("✓ 视频处理和英文字幕生成完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤1，返回主菜单。")
            return None
        raise
    except Exception as e:
        raise Exception("视频处理和英文字幕生成失败")

def step2(processor):
    print("\n=== 步骤2: 合并英文字幕片段 ===")
    try:
        if not processor.merger.process():
            raise Exception("英文字幕合并失败")
        print("✓ 英文字幕合并完成")
    except Exception as e:
        raise Exception("英文字幕合并失败")

def step2_1(processor):
    print("\n=== 步骤2-1: 下载YouTube英文字幕文件 ===")
    try:
        downloader = YouTubeSubtitleDownloader(processor.output_folder)
        result = downloader.process()
        if result:
            print("✓ YouTube英文字幕下载完成")
        else:
            raise Exception("YouTube英文字幕下载失败")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤2-1，返回主菜单。")
            return None
        raise
    except Exception as e:
        raise Exception("YouTube英文字幕下载失败")

def step3(processor):
    print("\n=== 步骤3: 分割字幕为多个部分 ===")
    try:
        num_parts_split = get_num_parts("请输入要分割成的Part数量", 10)
        parts_list = create_parts_list(num_parts_split)
        processor.parts_list = parts_list  # 先设置parts_list，即使后续处理失败也能保持
        
        processor.splitter = SubtitleSplitter(parts_list, processor.output_folder)
        if not processor.splitter.process():
            raise Exception("字幕分割失败")
        print("✓ 字幕分割完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤3，返回主菜单。")
            return None
        raise
    except Exception as e:
        raise Exception("字幕分割失败")

def step4(processor):
    print("\n=== 步骤4: 第一轮中文翻译（有英文、直译） ===")
    try:
        parts_list = auto_detect_parts_list(processor)
        
        part_names_translate1 = get_part_numbers("请输入要翻译的Part编号（第一轮翻译）", parts_list)
        processor.first_translator = FirstRoundTranslator(part_names_translate1, processor.output_folder)
        if not processor.first_translator.process():
            raise Exception("第一轮中文翻译失败")
        print("✓ 第一轮中文翻译完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤4，返回主菜单。")
            return None
        raise
    except Exception as e:
        # 如果是auto_detect_parts_list的异常，直接传递
        if "未找到有效的分割文件" in str(e) or "请先执行步骤3分割字幕" in str(e):
            raise
        raise Exception("第一轮中文翻译失败")

def step5(processor):
    print("\n=== 步骤5: 第二轮中文翻译（直译+意译，意译） ===")
    try:
        parts_list = auto_detect_parts_list(processor)
        
        part_names_translate2 = get_part_numbers("请输入要翻译的Part编号（第二轮翻译）", parts_list)
        processor.second_translator = SecondRoundTranslator(part_names_translate2, processor.output_folder)
        if not processor.second_translator.process():
            raise Exception("第二轮中文翻译失败")
        print("✓ 第二轮中文翻译完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤5，返回主菜单。")
            return None
        raise
    except Exception as e:
        # 如果是auto_detect_parts_list的异常，直接传递
        if "未找到有效的分割文件" in str(e) or "请先执行步骤3分割字幕" in str(e):
            raise
        raise Exception("第二轮中文翻译失败")


    
def step6(processor):
    print("\n=== 步骤6: 将很长的中文分屏分行 ===")
    try:
        parts_list = auto_detect_parts_list(processor)
        
        part_names_split = get_part_numbers("请输入要分屏分行处理的Part编号", parts_list)
        processor.third_translator = SplitTranslator(part_names_split, processor.output_folder)
        if not processor.third_translator.process():
            raise Exception("中文分屏分行失败")
        print("✓ 中文分屏分行完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤6，返回主菜单。")
            return None
        raise
    except Exception as e:
        # 如果是auto_detect_parts_list的异常，直接传递
        if "未找到有效的分割文件" in str(e) or "请先执行步骤3分割字幕" in str(e):
            raise
        raise Exception("中文分屏分行失败")

def step7(processor):
    print("\n=== 步骤7: 上传字幕到YouTube ===")
    try:
        parts_list = auto_detect_parts_list(processor)
        
        part_names_upload = get_part_numbers("请输入要上传的Part编号", parts_list)
        youtube_url = get_youtube_url()
        processor.uploader = SubtitleUploader(part_names_upload, processor.output_folder, youtube_url)
        if not processor.uploader.process():
            raise Exception("字幕上传失败")
        print("✓ 字幕上传完成")
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤7，返回主菜单。")
            return None
        raise
    except Exception as e:
        # 如果是auto_detect_parts_list的异常，直接传递
        if "未找到有效的分割文件" in str(e) or "请先执行步骤3分割字幕" in str(e):
            raise
        raise Exception("字幕上传失败")

def step8(processor):
    print("\n=== 步骤8: 下载YouTube Parts字幕, 合并,上传字幕到YouTube ===")
    try:
        # 询问用户有多少个parts，默认值为10
        num_parts = get_num_parts("请输入要处理的Part数量", 10)
        parts_list = create_parts_list(num_parts)
        
        # 正确调用Step7_FinalDownloadUpload.main(parts_list)
        import Step8_FinalDownloadUpload
        result = Step8_FinalDownloadUpload.main(parts_list)
        
        # 检查返回值
        if result is None:
            print("用户选择退出步骤8，返回主菜单。")
            return None
        elif result is False:
            raise Exception("步骤8执行失败")
        else:
            print("✓ 步骤8执行完成")
            
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤8，返回主菜单。")
            return None
        raise
    except Exception as e:
        print(f"Step8 执行出错: {e}")
        raise Exception("步骤8执行失败")

def step9(processor):
    print("\n=== 步骤9: 合并本地Part字幕为PartAll-Step4-All, PartAll-Step5-All ===")
    try:
        merger = PartAllMerger(processor.output_folder)
        result = merger.process()
        if result:
            print("✓ Part文件合并完成")
        else:
            raise Exception("Part文件合并失败")
    except Exception as e:
        raise Exception("Part文件合并失败")

def step10(processor):
    print("\n=== 步骤10: 将老数据文件移到OldFiles ===")
    try:
        mover = OldFilesMover(processor.output_folder)
        result = mover.process()
        if result is None:
            print("用户选择退出步骤10，返回主菜单。")
            return None
        elif result:
            print("✓ 老数据文件处理完成")
        else:
            raise Exception("老数据文件处理失败")
    except Exception as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤10，返回主菜单。")
            return None
        raise Exception("老数据文件处理失败")

def show_menu():
    print("\n== 马鞍峰教会中文堂字幕处理主菜单  2025-09-07==")
    print("")
    print("1: 处理视频并生成英文字幕")
    print("2: 合并英文字幕片段")
    print("2-1: 下载YouTube英文字幕文件")
    print("3: 分割字幕为多个部分")
    print("4: 第一轮中文翻译（有英文、直译）")
    print("5: 第二轮中文翻译（直译+意译， 意译）")    
    print("6: 将很长的中文分屏分行")
    print("7: 上传字幕到YouTube")
    print("8: 下载YouTube Parts字幕,合并,上传字幕到YouTube")
    print("9: 合并第二轮中文翻译为一个文件")
    print("10: 将老数据文件移到OldFiles")
    print("X: 退出程序")
    print("\n")
    print("==============================================")



def main():
    try:
        output_folder = 'DataFiles'
        processor = SubtitleProcessor(output_folder)
        processor.parts_list = None  # 用于存储分割后的 parts_list
        while True:
            show_menu()
            choice = input("请选择要执行的步骤编号（或X退出）：").strip()
            
            # 处理中文输入模式下的英文字符识别
            choice_clean = clean_input_for_comparison(choice)
            if choice_clean == 'x':
                print("已退出程序。")
                break
            elif choice in {'1','2','2-1','3','4','5','6','7','8','9','10'}:
                try:
                    result = None
                    if choice == '1':
                        result = step1(processor)
                    elif choice == '2':
                        result = step2(processor)
                    elif choice == '2-1':
                        result = step2_1(processor)
                    elif choice == '3':
                        result = step3(processor)
                    elif choice == '4':
                        result = step4(processor)
                    elif choice == '5':
                        result = step5(processor)
                    elif choice == '6':
                        result = step6(processor)
                    elif choice == '7':
                        result = step7(processor)
                    elif choice == '8':
                        result = step8(processor)
                    elif choice == '9':
                        result = step9(processor)
                    elif choice == '10':
                        result = step10(processor)
                    
                    # 如果步骤函数返回None（用户退出），直接继续循环
                    if result is None:
                        continue
                        
                except Exception as e:
                    print(f"\n处理过程中出错: {str(e)}")
                    traceback.print_exc()
                continue
            else:
                print("无效输入，请重新选择。")
    except Exception as e:
        print(f"\n程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main() 