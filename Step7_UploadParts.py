######################################################################
#  COPYRIGHT 2023-24 
#  上传字幕到 Youtube 中
######################################################################
import os
import traceback
from typing import Dict, Optional, List
from googleapiclient.discovery import build 
from googleapiclient.http import MediaFileUpload
from common_utils import (
    subtitle_token, extract_video_id, get_output_folder
)

CONFIG_FILENAME = "configuration.txt"
DEFAULT_OUTPUT_FOLDER = "DataFiles"  # Set this to a specific folder name if you want to override the date-based folder

# 文件名配置
# Step4文件后缀
PART_CH1_STEP4_SUFFIX = "-Step4.sbv"  # Step4第一轮翻译版本
PART_CH1_STEP4_NO_PUNCTUATION_SUFFIX = "-Step4-english-chinese.sbv"  # Step4无标点版本
# Step5文件后缀
PART_CH2_STEP5_CHINESE_MEANING_SUFFIX = "-Step5-chinese_meaning.sbv"  # Step5直译+意译版本
PART_CH2_STEP5_MEANING_ONLY_SUFFIX = "-Step5-meaning_only.sbv"  # Step5只意译版本
PART_CH2_STEP5_ALL_SUFFIX = "-Step5-all.sbv"  # Step5英文+中文+意译版本
# Step6文件后缀
PART_CH2_STEP6_CHINESE_MEANING_SUFFIX = "-Step6-chinese_meaning.sbv"  # Step6直译+意译版本
PART_CH2_STEP6_MEANING_ONLY_SUFFIX = "-Step6-meaning_only.sbv"  # Step6只意译版本
PART_CH2_STEP6_ALL_SUFFIX = "-Step6-all.sbv"  # Step6英文+中文+意译版本
PART_UPLOAD_SUFFIX = "-Step7.sbv"  # 上传用的字幕文件后缀
INPUT_PREFIX = ""  # 输入文件前缀
OUTPUT_PREFIX = ""  # 输出文件前缀

# 上传配置
DEFAULT_YOUTUBE_URL = "https://www.youtube.com/watch?v=default_video_id"  # 默认YouTube URL
UPLOAD_LANGUAGE = "zh-Hans"  # 上传字幕的语言代码
TEST_LANGUAGE = "zh-CN"  # 测试字幕的语言代码
INCLUDE_ENGLISH = True  # 是否包含英文字幕

class SubtitleUploader:
    def __init__(self, parts: List[str], output_folder: str, youtube_url: str = DEFAULT_YOUTUBE_URL):
        self.output_folder = output_folder
        self.youtube_url = youtube_url
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")
        
        self.include_english = INCLUDE_ENGLISH
        
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
        # Step4文件后缀
        self.part_ch1_step4_suffix = PART_CH1_STEP4_SUFFIX
        self.part_ch1_step4_no_punctuation_suffix = PART_CH1_STEP4_NO_PUNCTUATION_SUFFIX
        # Step5文件后缀
        self.part_ch2_step5_chinese_meaning_suffix = PART_CH2_STEP5_CHINESE_MEANING_SUFFIX
        self.part_ch2_step5_meaning_only_suffix = PART_CH2_STEP5_MEANING_ONLY_SUFFIX
        self.part_ch2_step5_all_suffix = PART_CH2_STEP5_ALL_SUFFIX
        # Step6文件后缀
        self.part_ch2_step6_chinese_meaning_suffix = PART_CH2_STEP6_CHINESE_MEANING_SUFFIX
        self.part_ch2_step6_meaning_only_suffix = PART_CH2_STEP6_MEANING_ONLY_SUFFIX
        self.part_ch2_step6_all_suffix = PART_CH2_STEP6_ALL_SUFFIX
        self.part_upload_suffix = PART_UPLOAD_SUFFIX
        self.input_prefix = INPUT_PREFIX
        self.output_prefix = OUTPUT_PREFIX
        
        # 使用常量定义的上传设置
        self.upload_language = UPLOAD_LANGUAGE
        
        self.youtube = self._init_youtube()
        self.video_id = self._get_video_id()

    def _init_youtube(self):
        """初始化YouTube API客户端"""
        creds = subtitle_token()
        return build('youtube', 'v3', credentials=creds)

    def _get_video_id(self) -> str:
        """获取视频ID"""
        video_id = extract_video_id(self.youtube_url)
        if not video_id:
            raise ValueError(f"无效的YouTube URL: {self.youtube_url}")
            
        return video_id

    def _detect_input_files(self, part_name: str) -> List[tuple]:
        """检测Part的输入文件，返回文件列表"""
        part_name_capitalized = part_name.capitalize()
        files = []
        
        # 检测Step4文件
        step4_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch1_step4_suffix}")
        if os.path.exists(step4_file):
            files.append((step4_file, f"{part_name_capitalized}-Step4.sbv"))
        
        step4_no_punctuation_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch1_step4_no_punctuation_suffix}")
        if os.path.exists(step4_no_punctuation_file):
            files.append((step4_no_punctuation_file, f"{part_name_capitalized}-Step4-english-chinese.sbv"))
        
        # 检测Step5文件
        step5_chinese_meaning_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_step5_chinese_meaning_suffix}")
        step5_meaning_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_step5_meaning_only_suffix}")
        step5_all_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_step5_all_suffix}")
        step5_chinese_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}-Step5-chinese_only.sbv")
        
        if os.path.exists(step5_chinese_meaning_file):
            files.append((step5_chinese_meaning_file, f"{part_name_capitalized}-Step5-chinese_meaning.sbv"))
        if os.path.exists(step5_meaning_only_file):
            files.append((step5_meaning_only_file, f"{part_name_capitalized}-Step5-meaning_only.sbv"))
        if os.path.exists(step5_all_file):
            files.append((step5_all_file, f"{part_name_capitalized}-Step5-all.sbv"))
        if os.path.exists(step5_chinese_only_file):
            files.append((step5_chinese_only_file, f"{part_name_capitalized}-Step5-chinese_only.sbv"))
        
        # 检测Step6文件
        step6_meaning_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_ch2_step6_meaning_only_suffix}")
        step6_chinese_only_file = os.path.join(self.output_folder, f"{part_name_capitalized}-Step6-chinese_only.sbv")
        
        if os.path.exists(step6_meaning_only_file):
            files.append((step6_meaning_only_file, f"{part_name_capitalized}-Step6-meaning_only.sbv"))
        if os.path.exists(step6_chinese_only_file):
            files.append((step6_chinese_only_file, f"{part_name_capitalized}-Step6-chinese_only.sbv"))
        
        return files

    def _get_user_choice(self, part_name: str, files: List[tuple]) -> tuple:
        """让用户选择要上传的文件"""
        if not files:
            print(f"\n{part_name} 没有找到可用的字幕文件")
            return None
        
        print(f"\n{part_name} 发现以下字幕文件:")
        
        # 动态显示可用的文件选项
        options = []
        
        for i, file in enumerate(files):
            file_name = file[1]  # 获取文件名
            
            # Step4文件选项
            if 'Step4-english-chinese' in file_name:
                options.append((str(i + 1), i, 'Step4-英中无标点版本'))
            elif 'Step4' in file_name and 'Step' not in file_name.replace('Step4', ''):
                options.append((str(i + 1), i, 'Step4-第一轮翻译版本'))
            # Step5文件选项
            elif 'Step5-chinese_meaning' in file_name:
                options.append((str(i + 1), i, 'Step5-直译+意译版本'))
            elif 'Step5-meaning_only' in file_name:
                options.append((str(i + 1), i, 'Step5-只意译版本'))
            elif 'Step5-chinese_only' in file_name:
                options.append((str(i + 1), i, 'Step5-只直译版本'))
            elif 'Step5-all' in file_name:
                options.append((str(i + 1), i, 'Step5-英文+中文+意译版本'))
            # Step6文件选项
            elif 'Step6-chinese_only' in file_name:
                options.append((str(i + 1), i, 'Step6-只直译版本'))
            elif 'Step6-meaning_only' in file_name:
                options.append((str(i + 1), i, 'Step6-只意译版本'))
            else:
                # 如果都不匹配，显示文件名
                options.append((str(i + 1), i, file_name))
        
        # 显示所有可用选项
        for num, file_index, desc in options:
            print(f"{num}: {desc}")
        
        while True:
            choice = input(f"请选择要上传的文件 (1-{len(files)}): ").strip()
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(files):
                    return files[choice_num - 1]
                else:
                    print(f"无效选择，请输入 1-{len(files)} 之间的数字")
            except ValueError:
                print(f"无效输入，请输入 1-{len(files)} 之间的数字")

    def _upload_subtitle(self, subtitle_path: str, language: str, name: str) -> bool:
        """上传单个字幕文件"""
        try:
            # 检查是否已存在相同语言和名称的字幕
            captions_list_response = self.youtube.captions().list(
                part="snippet",
                videoId=self.video_id
            ).execute()

            # 查找并删除同名字幕
            for item in captions_list_response.get('items', []):
                if (item['snippet']['language'] == language and 
                    item['snippet']['name'] == name):
                    self.youtube.captions().delete(id=item['id']).execute()
                    print(f"        已删除旧字幕: {name}")
                    break

            # 上传新字幕
            request = self.youtube.captions().insert(
                part='snippet',
                body={
                    'snippet': {
                        'videoId': self.video_id,
                        'language': language,
                        'name': name,
                        'isDraft': False,
                        "format": "sbv"
                    }
                },
                media_body=MediaFileUpload(subtitle_path)
            )
            response = request.execute()

            if response['snippet']['status'] == 'failed':
                error_reason = response['snippet'].get('failureReason', '未知原因')
                print(f"\n        字幕上传失败: {name}")
                print(f"        失败原因: {error_reason}")
                print(f"        字幕语言: {language}")
                print(f"        字幕格式: sbv")
                print(f"        字幕文件: {subtitle_path}")
                print(f"        视频ID: {self.video_id}")
                return False
            else:
                print(f"        字幕上传成功: {name}")
                return True

        except Exception as e:
            print(f"\n        上传字幕时出错: {name}")
            print(f"        错误类型: {type(e).__name__}")
            print(f"        错误信息: {str(e)}")
            print(f"        字幕语言: {language}")
            print(f"        字幕文件: {subtitle_path}")
            print(f"        视频ID: {self.video_id}")
            
            # 输出HTTP错误详情
            if hasattr(e, 'resp'):
                if hasattr(e.resp, 'status'):
                    print(f"        HTTP状态码: {e.resp.status}")
                if hasattr(e.resp, 'data'):
                    try:
                        error_data = e.resp.data.decode('utf-8')
                        print(f"        错误详情: {error_data}")
                    except:
                        print(f"        错误详情: {e.resp.data}")
            
            # 输出配额信息
            if hasattr(e, 'resp') and hasattr(e.resp, 'status') and e.resp.status == 403:
                print("\n        配额相关建议:")
                print("        1. 检查API密钥是否有效")
                print("        2. 检查API配额是否已用完")
                print("        3. 等待配额重置（通常24小时）")
                print("        4. 使用新的API密钥")
            
            traceback.print_exc()
            return False

    def _create_test_subtitle(self, part_name: str) -> str:
        """创建测试字幕文件"""
        test_content = "00:00:00.000,00:00:04.310\nTest only"
        # 将part1转换为Part1格式
        part_name_capitalized = part_name.capitalize()
        test_file_path = os.path.join(self.output_folder, f"{part_name_capitalized}_test.sbv")
        with open(test_file_path, 'w', encoding='utf-8') as f:
            f.write(test_content)
        return test_file_path

    def process(self) -> bool:
        """主处理函数"""
        try:
            print(f"视频ID: {self.video_id}")
            print(f"需要处理的Part数量: {len(self.parts)}")
            
            success_count = 0
            # 处理每个Part
            for part_name in self.parts:
                try:
                    print(f"\n处理 {part_name}")
                    
                    # 检测输入文件
                    files = self._detect_input_files(part_name)
                    
                    if not files:
                        print(f"        未找到任何字幕文件")
                        continue
                    
                    # 让用户选择要上传的文件
                    selected_file = self._get_user_choice(part_name, files)
                    if selected_file is None:
                        print(f"        用户取消选择，跳过 {part_name}")
                        continue
                    
                    subtitle_file, file_name = selected_file
                    print(f"        用户选择: {file_name}")
                    print(f"        使用文件: {subtitle_file}")
                    
                    # 上传简体中文字幕
                    if self._upload_subtitle(subtitle_file, self.upload_language, part_name):
                        success_count += 1
                        
                        # 创建并上传测试字幕到 Chinese (China)
                        test_file = self._create_test_subtitle(part_name)
                        self._upload_subtitle(test_file, TEST_LANGUAGE, part_name)
                        os.remove(test_file)  # 删除临时测试文件
                    
                except Exception as e:
                    print(f"处理 {part_name} 时出错: {str(e)}")
                    traceback.print_exc()
                    continue
            
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
            
        uploader = SubtitleUploader(parts, output_folder)
        result = uploader.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()