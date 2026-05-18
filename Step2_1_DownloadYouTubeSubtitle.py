######################################################################
#  COPYRIGHT 2023-24 
#  下载YouTube英文字幕文件
######################################################################
import os
import re
from typing import Optional, List, Dict

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

def extract_video_id(url: str) -> Optional[str]:
    """从YouTube URL中提取视频ID"""
    # 支持多种YouTube URL格式
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
        r'youtube\.com/watch\?.*v=([^&\n?#]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def get_video_info(video_id: str) -> Optional[Dict]:
    """获取视频信息"""
    try:
        # 使用YouTube Data API v3获取视频信息
        # 注意：这里使用无API密钥的方式，可能有限制
        url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 提取视频标题
        title_match = re.search(r'<title>(.*?)</title>', response.text)
        title = title_match.group(1).replace(' - YouTube', '') if title_match else f"Video_{video_id}"
        
        return {
            'video_id': video_id,
            'title': title,
            'url': url
        }
    except Exception as e:
        print(f"获取视频信息失败: {e}")
        return None

def get_available_captions(video_id: str) -> List[Dict]:
    """获取可用的字幕列表 - 使用YouTube API"""
    try:
        # 使用YouTube API获取字幕列表
        from googleapiclient.discovery import build
        from common_utils import subtitle_token
        
        # 初始化YouTube API客户端
        creds = subtitle_token()
        youtube = build('youtube', 'v3', credentials=creds)
        
        # 获取字幕列表
        captions_list_response = youtube.captions().list(
            part="snippet",
            videoId=video_id
        ).execute()
        
        captions = []
        for item in captions_list_response.get('items', []):
            snippet = item['snippet']
            captions.append({
                'id': item['id'],
                'language': snippet['language'],
                'name': snippet.get('name', ''),
                'trackKind': snippet.get('trackKind', ''),
                'isAutoSynced': snippet.get('isAutoSynced', False),
                'isCC': snippet.get('isCC', False),
                'isLarge': snippet.get('isLarge', False),
                'isEasyReader': snippet.get('isEasyReader', False),
                'isDraft': snippet.get('isDraft', False),
                'isTranslatable': snippet.get('isTranslatable', False)
            })
        
        return captions
        
    except Exception as e:
        print(f"获取字幕列表失败: {e}")
        return []

def download_caption(caption_id: str) -> Optional[str]:
    """从YouTube下载字幕内容 - 使用YouTube API"""
    try:
        from googleapiclient.discovery import build
        from common_utils import subtitle_token
        
        # 初始化YouTube API客户端
        creds = subtitle_token()
        youtube = build('youtube', 'v3', credentials=creds)
        
        # 下载字幕
        subtitle = youtube.captions().download(
            id=caption_id,
            tfmt='sbv'
        ).execute()

        return subtitle.decode('utf-8')

    except Exception as e:
        print(f"下载字幕失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_sbv_content(content: str) -> str:
    """解析SBV格式的字幕内容，保持原始格式"""
    # 直接返回内容，因为YouTube API已经返回SBV格式
    return content

def format_time(seconds: float) -> str:
    """将秒数转换为SBV时间格式 (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"

class YouTubeSubtitleDownloader:
    def __init__(self, output_folder: str = '.'):
        self.output_folder = output_folder
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")
    
    def get_youtube_url(self) -> str:
        """获取用户指定的YouTube URL"""
        print("\n请指定要下载字幕的YouTube视频URL：")
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
    
    def process(self) -> bool:
        """主处理函数"""
        try:
            print("\n=== 步骤2-1: 下载YouTube英文字幕文件 ===")
            
            # 获取YouTube URL
            youtube_url = self.get_youtube_url()
            
            # 提取视频ID
            video_id = extract_video_id(youtube_url)
            if not video_id:
                raise Exception("无法从URL中提取视频ID")
            
            print(f"视频ID: {video_id}")
            
            # 获取视频信息
            video_info = get_video_info(video_id)
            if video_info:
                print(f"视频标题: {video_info['title']}")
            
            # 获取可用字幕
            print("\n正在获取可用字幕...")
            captions = get_available_captions(video_id)
            
            if not captions:
                raise Exception("未找到任何字幕")
            
            # 显示可用字幕
            print(f"\n找到 {len(captions)} 个字幕:")
            for i, caption in enumerate(captions, 1):
                language_info = f"{caption['language']}"
                if caption['name']:
                    language_info += f" - {caption['name']}"
                if caption['isAutoSynced']:
                    language_info += " (自动生成)"
                if caption['isCC']:
                    language_info += " (CC)"
                print(f"{i}: {language_info}")
            
            # 查找英文字幕
            english_caption = None
            for caption in captions:
                if caption['language'].lower() in ['en', 'en-us', 'en-gb']:
                    english_caption = caption
                    break
            
            if not english_caption:
                # 如果没有找到英文字幕，让用户选择
                print("\n未找到英文字幕，请选择要下载的字幕:")
                for i, caption in enumerate(captions, 1):
                    language_info = f"{caption['language']}"
                    if caption['name']:
                        language_info += f" - {caption['name']}"
                    if caption['isAutoSynced']:
                        language_info += " (自动生成)"
                    if caption['isCC']:
                        language_info += " (CC)"
                    print(f"{i}: {language_info}")
                
                while True:
                    choice = input("请选择字幕编号: ").strip()
                    try:
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(captions):
                            english_caption = captions[choice_num - 1]
                            break
                        else:
                            print("无效选择，请重新输入")
                    except ValueError:
                        print("请输入有效的数字")
            else:
                language_info = f"{english_caption['language']}"
                if english_caption['name']:
                    language_info += f" - {english_caption['name']}"
                if english_caption['isAutoSynced']:
                    language_info += " (自动生成)"
                if english_caption['isCC']:
                    language_info += " (CC)"
                print(f"\n找到英文字幕: {language_info}")
            
            # 下载字幕
            print(f"\n正在下载字幕...")
            caption_content = download_caption(english_caption['id'])
            
            if not caption_content:
                raise Exception("下载字幕失败")
            
            # 解析SBV内容
            print("正在解析字幕内容...")
            sbv_content = parse_sbv_content(caption_content)
            
            if not sbv_content:
                raise Exception("解析字幕内容失败")
            
            # 保存文件
            output_file = os.path.join(self.output_folder, "step2_merged_en.sbv")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(sbv_content)
            
            print(f"\n✓ 字幕下载完成")
            print(f"保存到: {output_file}")
            
            # 显示统计信息
            lines = sbv_content.strip().split('\n')
            subtitle_count = len([line for line in lines if ',' in line and ':' in line])
            print(f"字幕片段数量: {subtitle_count}")
            
            return True
            
        except Exception as e:
            print(f"处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def main():
    try:
        downloader = YouTubeSubtitleDownloader()
        result = downloader.process()
        
        if result:
            print("处理完成")
        else:
            print("处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
