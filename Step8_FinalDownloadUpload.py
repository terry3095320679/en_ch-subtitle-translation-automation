######################################################################
#  COPYRIGHT 2023-24 
#  下载Youtube字幕，合并后重新上传
######################################################################
import os
import traceback
from typing import List, Dict, Optional
from googleapiclient.discovery import build 
from googleapiclient.http import MediaFileUpload
from common_utils import (
    SubtitleSegment, save_sbv_file, 
    subtitle_token, extract_video_id, parse_time, format_time, clean_part_name,
    get_user_output_folder
)

DEFAULT_OUTPUT_FOLDER = "DataFiles"


# 文件名配置
PART_CH3_SUFFIX = "-Step8.sbv"  # 第三轮中文字幕文件后缀
MERGED_CH_FILENAME = "step8_final_merged_ch.sbv"  # 合并后的中文字幕文件名
INPUT_PREFIX = ""  # 输入文件前缀（来自Step6）
OUTPUT_PREFIX = ""  # 输出文件前缀


class SubtitleDownloadUploader:
    def __init__(self, parts: List[str], youtube_url: str, output_dir: str = DEFAULT_OUTPUT_FOLDER):
        self.youtube_url = youtube_url
        
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
        
        # 设置默认值
        self.download_part_language = 'zh-CN'
        self.final_upload_language = 'zh-CN'
        self.final_upload_name = 'China'
        self.merged_ch_filename = MERGED_CH_FILENAME
        self.part_ch3_suffix = PART_CH3_SUFFIX
        self.input_prefix = INPUT_PREFIX
        self.output_prefix = OUTPUT_PREFIX
        
        # 设置输出目录
        self.output_dir = output_dir if output_dir else DEFAULT_OUTPUT_FOLDER
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"创建输出目录: {self.output_dir}")
        
        # 初始化YouTube客户端并获取视频ID
        self.youtube = self._init_youtube()
        self.video_id = self._get_video_id()

    def _init_youtube(self):
        """初始化YouTube API客户端"""
        creds = subtitle_token()
        return build('youtube', 'v3', credentials=creds)

    def _get_video_id(self) -> str:
        """获取视频ID"""
        if not self.youtube_url:
            raise ValueError("配置文件必须包含 'youtubeurl' 配置项")
            
        video_id = extract_video_id(self.youtube_url)
        if not video_id:
            raise ValueError(f"无效的YouTube URL: {self.youtube_url}")
            
        return video_id

    def _download_subtitle(self, caption_id: str) -> Optional[str]:
        """从YouTube下载字幕内容"""
        try:
            subtitle = self.youtube.captions().download(
                id=caption_id,
                tfmt='sbv'
            ).execute()

            return subtitle.decode('utf-8')

        except Exception as e:
            print(f"        下载字幕时出错: {str(e)}")
            traceback.print_exc()
            return None

    def _parse_sbv_content(self, content: str) -> List[SubtitleSegment]:
        """解析SBV格式的字幕内容，保持原始换行符"""
        segments = []
        lines = content.split('\n')
        current_times = None
        current_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_times and current_text:
                    start_time, end_time = current_times
                    # 使用换行符连接文本行，而不是空格
                    segments.append(SubtitleSegment(
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
            segments.append(SubtitleSegment(
                start_time=start_time,
                end_time=end_time,
                text='\n'.join(current_text)  # 使用换行符连接文本行
            ))
        
        return segments

    def _merge_subtitles(self, segments_list: List[List[SubtitleSegment]]) -> List[SubtitleSegment]:
        """合并并按时间排序字幕片段"""
        all_segments = []
        for segments in segments_list:
            all_segments.extend(segments)
        
        # 按开始时间排序
        sorted_segments = sorted(all_segments, key=lambda x: parse_time(x.start_time))
        
        # 确保每个片段的结束时间不大于下一个片段的开始时间
        for i in range(len(sorted_segments) - 1):
            current_segment = sorted_segments[i]
            next_segment = sorted_segments[i + 1]
            
            current_end_time = parse_time(current_segment.end_time)
            next_start_time = parse_time(next_segment.start_time)
            
            # 如果当前片段的结束时间大于下一个片段的开始时间
            if current_end_time > next_start_time:
                # 将当前片段的结束时间调整为下一个片段开始时间
                adjusted_end_time = next_start_time
                if adjusted_end_time > parse_time(current_segment.start_time):  # 确保结束时间大于开始时间
                    print(f"调整片段{current_segment.start_time}结束时间: 从{current_segment.end_time} 调整为 {format_time(adjusted_end_time)}")                    
                    current_segment.end_time = format_time(adjusted_end_time)

        
        return sorted_segments

    def _upload_subtitle(self, subtitle_path: str, language: str, name: str) -> bool:
        """上传字幕到YouTube"""
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
                        'isDraft': False
                    }
                },
                media_body=MediaFileUpload(subtitle_path)
            )
            response = request.execute()

            if response['snippet']['status'] == 'failed':
                print(f"        字幕上传失败: {response['snippet'].get('failureReason', '未知原因')}")
                return False
            else:
                print(f"        字幕上传成功: {name}")
                return True

        except Exception as e:
            print(f"        上传字幕时出错: {str(e)}")
            traceback.print_exc()
            return False

    def process(self) -> bool:
        """主处理函数"""
        try:
            if not self.parts:
                print("没有找到任何已上传的字幕部分，退出程序")
                return False
                
            print(f"视频ID: {self.video_id}")
            print(f"需要处理的Part数量: {len(self.parts)}")
            
            # 获取所有字幕列表
            print("\n获取字幕列表...")
            captions_list_response = self.youtube.captions().list(
                part="snippet",
                videoId=self.video_id
            ).execute()
            
            # 创建字幕ID映射
            caption_id_map = {}
            for item in captions_list_response['items']:
                if item['snippet']['language'] == self.download_part_language:
                    clean_youtube_name = clean_part_name(item['snippet']['name'])
                    caption_id_map[clean_youtube_name] = item['id']
            
            # 下载所有Part的字幕
            all_segments_list = []
            for part_name in self.parts:
                try:
                    print(f"\n下载 {part_name} 的字幕")
                    cleaned_part_name = clean_part_name(part_name)
                    
                    # 获取对应的caption_id
                    caption_id = caption_id_map.get(cleaned_part_name)
                    if not caption_id:
                        print(f"        未找到字幕: {part_name}")
                        continue
                        
                    subtitle_content = self._download_subtitle(caption_id)
                    
                    if subtitle_content:
                        segments = self._parse_sbv_content(subtitle_content)
                        print(f"        成功下载 {len(segments)} 个字幕片段")
                        
                        # 保存下载的字幕到文件
                        # 将part1转换为Part1格式
                        part_name_capitalized = part_name.capitalize()
                        part_file = os.path.join(self.output_dir, f"{part_name_capitalized}{self.part_ch3_suffix}")
                        save_sbv_file(segments, part_file)
                        print(f"        已保存下载的字幕: {part_file}")
                        
                        all_segments_list.append(segments)
                    
                except Exception as e:
                    print(f"处理 {part_name} 时出错: {str(e)}")
                    traceback.print_exc()
                    continue
            
            if not all_segments_list:
                print("没有找到任何字幕，退出程序")
                return False
            
            # 合并字幕
            print("\n合并字幕...")
            merged_segments = self._merge_subtitles(all_segments_list)
            print(f"合并后共有 {len(merged_segments)} 个字幕片段")
            
            # 保存合并后的字幕
            merged_file = os.path.join(self.output_dir, self.merged_ch_filename)
            save_sbv_file(merged_segments, merged_file)
            print(f"已保存合并后的字幕: {merged_file}")
            
            # 上传合并后的字幕
            print("\n上传合并后的字幕...")
            ret = self._upload_subtitle(merged_file, self.final_upload_language, self.final_upload_name)
        
            # 检查合并字幕， 看看是否有任何两个相邻的片段的时间段重叠，如果有，则打印出来
            # 也检查是否有相邻的片段，时间间隔超过5秒钟， 如果有，则打印出来        
            for i in range(len(merged_segments)):
                if i > 0 and merged_segments[i].start_time < merged_segments[i-1].end_time:
                    print(f"        发现相邻片段时间端重叠: {merged_segments[i].start_time}  {merged_segments[i].end_time}")
                if i > 0 and parse_time(merged_segments[i].start_time) - parse_time(merged_segments[i-1].end_time) > 5:
                    print(f"        发现相邻片段时间间隔超过5秒: {merged_segments[i].start_time} - {merged_segments[i].end_time}")
                    
            return ret
            
        except Exception as e:
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return False

def get_youtube_url() -> str:
    """获取用户指定的YouTube URL"""
    print("\n请指定要下载字幕的YouTube视频URL：")
    print("(输入X退出当前步骤)")
    url = input().strip()
    
    # 处理中文输入模式下的英文字符识别
    url_clean = url.lower().strip()
    # 处理全角字符转换为半角字符
    full_to_half = {
        'ｘ': 'x', 'Ｘ': 'x',
        'ｙ': 'y', 'Ｙ': 'y',
        'ｎ': 'n', 'Ｎ': 'n',
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9'
    }
    
    for full, half in full_to_half.items():
        url_clean = url_clean.replace(full, half)
    
    if url_clean == 'x':
        raise ValueError("用户选择退出当前步骤")
    
    if not url:
        raise ValueError("必须提供YouTube视频URL")
    
    print(f"将使用指定的YouTube URL: {url}")
    return url

def main(parts_list=None):
    try:
        # 如果没有提供parts_list，使用默认的10个parts
        if parts_list is None:
            parts_list = [f"part{i}" for i in range(1, 11)]
        
        # 获取用户指定的YouTube URL
        youtube_url = get_youtube_url()
        
        processor = SubtitleDownloadUploader(parts_list, youtube_url)
        result = processor.process()
        
        print("处理完成" if result else "处理失败")
        return result
            
    except ValueError as e:
        if "用户选择退出" in str(e):
            print("用户选择退出步骤7，返回主菜单。")
            return None
        raise
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    main()