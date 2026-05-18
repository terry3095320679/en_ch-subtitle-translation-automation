######################################################################
#  COPYRIGHT 2023-24 
#  公共函数库
######################################################################
import os
import traceback
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials 
from google_auth_oauthlib.flow import InstalledAppFlow 
from datetime import datetime

# 添加在文件开头的常量定义部分
CHINESE_REPLACE_DICT = {
    "神": " 神",    
    "上帝": " 神",
    "“": "\"",  # 中文左引号替换为英文引号
    "”": "\"",  # 中文右引号替换为英文引号
    "‘": "\"",   # 中文左单引号替换为英文单引号
    "’": "\"",   # 中文右单引号替换为英文单引号
    "、": " ",   # 中文逗号替换为英文逗号
    "祈祷": "祷告",
    "庆祝康复": "CR",
    "工作": "事工",
    "嘿": "大家好",
    "服务": "敬拜",
    "校区": "分堂",
    "校园": "分堂",
    "棕枝主日": "棕榈枝主日",
    
    # 可以根据需要添加更多替换规则
}
@dataclass
class SubtitleSegment:
    """字幕片段数据类"""
    start_time: str
    end_time: str
    text: str

def parse_time(time_str: str) -> float:
    """将SBV时间戳转换为秒数"""
    hours, minutes, seconds = time_str.split(':')
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)

def format_time(seconds: float) -> str:
    """将秒数转换为SBV格式的时间戳"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

def is_sentence_end(text: str) -> bool:
    """判断文本是否以句子结束标点符号结尾"""
    end_markers = ['.', '!', '?', '."', '!"', '?"', '."', '!"', '?"']
    return any(text.strip().endswith(marker) for marker in end_markers)

def parse_sbv_file(file_path: str) -> List[SubtitleSegment]:
    """解析SBV文件，保持原始换行符"""
    segments = []
    current_times = None
    current_text = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()  # 只去除尾部空白，保留换行符
            if not line:
                if current_times and current_text:
                    segments.append(SubtitleSegment(
                        start_time=current_times[0],
                        end_time=current_times[1],
                        text='\n'.join(current_text)  # 使用换行符连接文本行
                    ))
                current_times = None
                current_text = []
            elif ',' in line and line.count(':') == 4:
                start, end = line.split(',')
                current_times = (start, end)
            else:
                current_text.append(line)
    
    # 处理最后一个片段
    if current_times and current_text:
        segments.append(SubtitleSegment(
            start_time=current_times[0],
            end_time=current_times[1],
            text='\n'.join(current_text)
        ))
    
    return segments

def save_sbv_file(segments: List[SubtitleSegment], file_path: str):
    """保存为SBV格式，保持换行符"""
    with open(file_path, 'w', encoding='utf-8') as f:
        for segment in segments:
            f.write(f"{segment.start_time},{segment.end_time}\n")
            f.write(f"{segment.text}\n\n")  # segment.text中的换行符会被保持

def read_config_file(filename: str) -> Dict[str, str]:
    """读取基本配置文件"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            config = {}
            for line in file:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                    
                # 使用任意空白字符（空格或制表符）作为分隔符
                parts = line.split(None, 1)  # None 表示使用任意空白字符作为分隔符
                if len(parts) == 2:  # 只处理有name和value的行
                    name, value = parts
                    config[name.lower()] = value.strip()
        return config
        
    except Exception as e:
        print(f"读取配置文件时出错: {str(e)}")
        traceback.print_exc()
        raise

def read_parts_config(filename: str) -> Tuple[str, List[str], bool]:
    """读取带Part信息的配置文件"""
    output_dir = ""
    parts = []
    include_english = False
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts_match = re.match(r'(?i)(part\d+)\s+\d{2}:\d{2}$', line)
                if parts_match:
                    part_name = parts_match.group(1).lower()
                    parts.append(part_name)
                    continue
                
                if ' ' in line:
                    key, value = line.split(' ', 1)
                    key = key.lower()
                    if key == 'outputfolder':
                        output_dir = value.strip()
                    elif key == 'include_english':
                        include_english = value.strip().lower() == 'yes'
        
        if not output_dir:
            raise ValueError("配置文件必须包含 'outputfolder' 配置项")
        return output_dir, parts, include_english
        
    except Exception as e:
        print(f"读取配置文件时出错: {str(e)}")
        raise

def subtitle_token() -> Credentials:
    """获取YouTube API认证令牌"""
    # Use environment variable to specify client secrets file to avoid hardcoding sensitive filenames
    # Set environment variable GOOGLE_CLIENT_SECRET_FILE to the path of your client secret JSON
    client_file = os.getenv('GOOGLE_CLIENT_SECRET_FILE', 'client_secret.json')
    scopes = ["https://www.googleapis.com/auth/youtube.force-ssl",
             "https://www.googleapis.com/auth/youtubepartner"]

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file('token.json', scopes)
    # Ensure token.json path is configurable via env to avoid committing tokens to repo
    token_path = os.getenv('GOOGLE_OAUTH_TOKEN_FILE', 'token.json')
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Require GOOGLE_CLIENT_SECRET_FILE env var to be set when running interactive auth
            client_file = os.getenv('GOOGLE_CLIENT_SECRET_FILE')
            if not client_file or not os.path.exists(client_file):
                raise FileNotFoundError("Google client secret file not found. Set GOOGLE_CLIENT_SECRET_FILE to your client_secret.json path")
            flow = InstalledAppFlow.from_client_secrets_file(client_file, scopes)
            creds = flow.run_local_server(port=0)
        # Save token to configurable path
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds

def extract_video_id(url: str) -> str:
    """从YouTube URL提取视频ID"""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def progress_hook(d):
    """下载进度回调函数"""
    if d['status'] == 'downloading':
        print(f"\r下载进度: {d['_percent_str'].strip()}", end='', flush=True)
    elif d['status'] == 'finished':
        print("\n下载完成，开始转换格式...")

def replace_chinese(text: str, replace_dict: dict = None) -> str:
    """
    替换文本中的中文标记为指定的新标记，并将所有不在英文双引号中的句号和逗号替换为空格。
    """
    import re
    try:
        if replace_dict is None:
            replace_dict = CHINESE_REPLACE_DICT
        # 替换所有出现的中文标记
        result = text
        for old_text, new_text in replace_dict.items():
            result = result.replace(old_text, new_text)

        # 用正则分割出所有引号内和引号外的内容
        # "[^"]*" 匹配引号内，[^"]+ 匹配引号外
        pattern = r'"[^"]*"|[^"]+'
        result = ''.join([
            m.group(0) if m.group(0).startswith('"') and m.group(0).endswith('"')
            else re.sub(r'[。，,]', ' ', m.group(0))
            for m in re.finditer(pattern, result)
        ])
        return result
    except Exception as e:
        print(f"替换中文标记时出错: {str(e)}")
        traceback.print_exc()
        return text  # 如果出错，返回原始文本

def save_sbv_subtitle(segments, filename):
    """将Whisper的segments保存为SBV格式"""
    with open(filename, 'w', encoding='utf-8') as f:
        for segment in segments:
            # 添加类型安全检查
            if hasattr(segment, 'start'):
                start = segment.start
                end = segment.end
                text = segment.text
            else:  # 兼容本地whisper的字典格式
                start = segment['start']
                end = segment['end'] 
                text = segment['text']
            
            # 替换中文标记    
            text = replace_chinese(text)
                
            start_time = format_time(start)
            end_time = format_time(end)
            f.write(f"{start_time},{end_time}\n{text.strip()}\n\n")

def merge_incomplete_sentences(segments: list) -> list:
    """合并未完成的句子片段"""
    if not segments:
        return segments

    merged = []
    current = segments[0].copy() if isinstance(segments[0], dict) else segments[0]
    
    for next_seg in segments[1:]:
        next_seg = next_seg.copy() if isinstance(next_seg, dict) else next_seg
        current_text = current.get('text', '') if isinstance(current, dict) else current.text
        
        if not is_sentence_end(current_text):
            # 如果当前片段不是句子结束，合并下一个片段
            if isinstance(current, dict):
                current['end'] = next_seg['end']
                current['text'] = current['text'].strip() + ' ' + next_seg['text'].strip()
            else:
                current.end = next_seg.end
                current.text = current.text.strip() + ' ' + next_seg.text.strip()
        else:
            # 当前片段是完整句子，保存并开始新片段
            merged.append(current)
            current = next_seg
    
    merged.append(current)
    return merged

def add_line_breaks(text):
    """在句子结束处添加换行符"""
    pattern = r'(?<=[.!?])"?\s+(?=[A-Z])'
    return re.sub(pattern, r'\n', text)

def save_srt_subtitle(segments, filename):
    """将segments保存为SRT格式
    SRT格式:
    1
    00:00:01,000 --> 00:00:04,000
    字幕内容1
    
    2
    00:00:05,000 --> 00:00:08,000
    字幕内容2
    """
    def format_srt_time(seconds: float) -> str:
        """将秒数转换为SRT格式的时间戳 (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        # SRT格式使用逗号分隔毫秒
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace('.', ',')

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for index, segment in enumerate(segments, 1):
                # 添加类型安全检查
                if hasattr(segment, 'start'):
                    start = segment.start
                    end = segment.end
                    text = segment.text
                else:  # 兼容本地whisper的字典格式
                    start = segment['start']
                    end = segment['end']
                    text = segment['text']
                
                # 替换中文标记
                text = replace_chinese(text)
                
                # 转换时间格式
                start_time = format_srt_time(start)
                end_time = format_srt_time(end)
                
                # 写入SRT格式
                f.write(f"{index}\n")  # 字幕序号
                f.write(f"{start_time} --> {end_time}\n")  # 时间行
                f.write(f"{text.strip()}\n\n")  # 文本内容和空行
                
        print(f"已保存SRT格式字幕: {filename}")
        return True
        
    except Exception as e:
        print(f"保存SRT字幕时出错: {str(e)}")
        traceback.print_exc()
        return False 

def clean_part_name(part_name: str) -> str:
    """
    清理Part名称，移除非Part前缀和数字后的任何字符
    
    Args:
        part_name: 要清理的Part名称
    
    Returns:
        清理后的标准Part名称
    
    Example:
        >>> clean_part_name("-Part 10")
        'part10'
        >>> clean_part_name("Part-10")
        'part10'
        >>> clean_part_name("Part 10")
        'part10'
    """
    try:
        # 转换为小写以统一处理
        part_name = part_name.lower()
        
        # 提取Part和数字部分
        match = re.match(r'^[^a-z]*part\s*(\d+)', part_name)
        if match:
            # 重新构建标准格式的Part名称
            return f"part{match.group(1)}"
        return part_name
        
    except Exception as e:
        print(f"清理Part名称时出错: {str(e)}")
        return part_name 

def save_srt_file(segments: List[SubtitleSegment], output_path: str) -> None:
    """保存字幕片段为SRT格式文件
    
    Args:
        segments: 字幕片段列表
        output_path: 输出文件路径
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, 1):
            # 写入序号
            f.write(f"{i}\n")
            
            # 转换时间格式 (0:00:00.000 -> 00:00:00,000)
            start_time = segment.start_time.replace('.', ',')
            end_time = segment.end_time.replace('.', ',')
            
            # 确保时间格式正确 (添加前导零)
            if len(start_time.split(':')[0]) == 1:
                start_time = '0' + start_time
            if len(end_time.split(':')[0]) == 1:
                end_time = '0' + end_time
                
            # 写入时间
            f.write(f"{start_time} --> {end_time}\n")
            
            # 写入文本
            f.write(f"{segment.text}\n\n") 

def parse_srt_content(content: str) -> List[SubtitleSegment]:
    """解析SRT格式的字幕内容
    
    Args:
        content: SRT格式的字幕内容字符串
    
    Returns:
        字幕片段列表
    """
    segments = []
    lines = content.split('\n')
    current_index = None
    current_times = None
    current_text = []
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_times and current_text:
                start_time, end_time = current_times
                segments.append(SubtitleSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text='\n'.join(current_text)
                ))
                current_index = None
                current_times = None
                current_text = []
            continue
        
        if not current_index and line.isdigit():
            current_index = int(line)
        elif not current_times and '-->' in line:
            start_time, end_time = line.split('-->')
            start_time = start_time.strip()
            end_time = end_time.strip()
            # 转换SRT时间格式为SBV格式 (00:00:00,000 -> 0:00:00.000)
            start_time = start_time.replace(',', '.')
            end_time = end_time.replace(',', '.')
            current_times = (start_time, end_time)
        elif current_times:
            current_text.append(line)
    
    # 处理最后一个片段
    if current_times and current_text:
        start_time, end_time = current_times
        segments.append(SubtitleSegment(
            start_time=start_time,
            end_time=end_time,
            text='\n'.join(current_text)
        ))
    
    return segments 

def get_output_folder(default_folder: str = "") -> str:
    """获取输出文件夹路径
    如果default_folder不为空，则使用default_folder
    否则使用 DataFiles 作为默认文件夹名
    """
    if default_folder:
        return default_folder
    # 使用 DataFiles 作为默认文件夹名
    return "DataFiles" 

def get_user_output_folder() -> str:
    """获取用户指定的输出文件夹"""
    print("\n请指定输出文件夹名称（直接回车将使用当前日期作为文件夹名）：")
    user_input = input().strip()
    
    if not user_input:
        # 使用当前日期作为文件夹名
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"将使用当前日期作为文件夹名: {today}")
        return today
    
    print(f"将使用指定的文件夹名: {user_input}")
    return user_input