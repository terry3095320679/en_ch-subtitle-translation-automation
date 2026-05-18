######################################################################
#  COPYRIGHT 2023-24 
#  Function：下载video ,取得英文的subtitle
######################################################################
import os
import sys
import traceback
import subprocess
from datetime import datetime
from openai import OpenAI
from pydub import AudioSegment
import logging
import yt_dlp
from typing import List, Optional, Dict, Any
from common_utils import (
    save_sbv_subtitle,
)
import glob
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_OUTPUT_FOLDER = "DataFiles"  # Set this to a specific folder name if you want to override the date-based folder
CURRENT_MODEL = "gpt-4o"  # gpt-3.5-turbo, text-davinci-002, gpt-4, gpt-3.5-turbo-1106, gpt-4o, gpt-4o-2024-05-13
MAX_AUDIO_SIZE_MB = 24
OPENAI_KEY  = "sk-xxxx"  # Redacted private OpenAI API key -> replaced with 'xxxx' for security

# 性能优化配置
ENABLE_CACHE = True  # 启用缓存，跳过已存在的文件
MAX_PARALLEL_CHUNKS = 3  # 并行处理的最大chunk数量（避免超过API限制）
SKIP_IF_OUTPUT_EXISTS = True  # 如果输出文件已存在则跳过处理

# 文件名配置
VIDEO_FILE = "video.mp4"  # 视频文件名
AUDIO_FILE = "step1_audio.wav"  # 音频文件名
ENGLISH_SBV_FILE = "step1_video_en.sbv"  # 英文字幕文件名
CHUNK_PREFIX = "step1_chunk_"  # 音频分块文件前缀

# 下载配置
DOWNLOAD_VIDEO_FILENAME = "video.mp4"  # 下载的视频文件名
DOWNLOAD_AUDIO_FILENAME = "step1_video.mp3"  # 下载的音频文件名
DOWNLOAD_SUBTITLE_FILENAME = "step1_video_en.sbv"  # 下载的字幕文件名

def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def estimate_transcription_time(file_size_mb: float) -> float:
    """估算转录时间（秒）
    基于经验：1MB音频大约需要15-30秒转录
    """
    return file_size_mb * 20  # 保守估计

def get_ffmpeg_path():
    """Get the path to ffmpeg executable, handling both development and packaged environments"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = os.path.dirname(sys.executable)
        if sys.platform == 'win32':
            ffmpeg_path = os.path.join(base_path, 'ffmpeg', 'ffmpeg.exe')
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
            ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
        elif sys.platform == 'darwin':
            ffmpeg_path = os.path.join(base_path, 'ffmpeg')
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
    else:
        # Running in development environment
        if sys.platform == 'win32':
            possible_paths = [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe'
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
        elif sys.platform == 'darwin':
            # Assume ffmpeg is installed via Homebrew or accessible via PATH
            return 'ffmpeg'

    return None

def get_ffprobe_path():
    """Get the path to ffprobe executable, handling both development and packaged environments"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = os.path.dirname(sys.executable)
        if sys.platform == 'win32':
            ffprobe_path = os.path.join(base_path, 'ffmpeg', 'ffprobe.exe')
            if os.path.exists(ffprobe_path):
                return ffprobe_path
            ffprobe_path = os.path.join(base_path, 'ffprobe.exe')
            if os.path.exists(ffprobe_path):
                return ffprobe_path
        elif sys.platform == 'darwin':
            ffprobe_path = os.path.join(base_path, 'ffprobe')
            if os.path.exists(ffprobe_path):
                return ffprobe_path
    else:
        # Running in development environment
        if sys.platform == 'win32':
            possible_paths = [
                r'C:\ffmpeg\bin\ffprobe.exe',
                r'C:\Program Files\ffmpeg\bin\ffprobe.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe'
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    return path
        elif sys.platform == 'darwin':
            # Assume ffprobe is installed via Homebrew or accessible via PATH
            return 'ffprobe'

    return None

# Set the ffmpeg and ffprobe paths for pydub
ffmpeg_path = get_ffmpeg_path()
ffprobe_path = get_ffprobe_path()

if ffmpeg_path:
    AudioSegment.converter = ffmpeg_path
if ffprobe_path:
    AudioSegment.ffprobe = ffprobe_path

class VideoProcessor:
    def __init__(self, output_folder: str):
        # 新增：自动查找DataFiles目录下最新的MP4文件
        self.output_folder = output_folder if output_folder and output_folder.strip() else 'DataFiles'
        # 初始化时不选择视频文件，等到 process() 时再选择
        self.video_file = None
        # 其它文件名常量
        self.audio_file = AUDIO_FILE
        self.english_sbv_file = ENGLISH_SBV_FILE
        self.chunk_prefix = CHUNK_PREFIX
        self.video_filename = DOWNLOAD_VIDEO_FILENAME
        self.audio_filename = DOWNLOAD_AUDIO_FILENAME
        self.subtitle_filename = DOWNLOAD_SUBTITLE_FILENAME
        
        # 确保输出目录存在
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"创建输出目录: {self.output_folder}")
        
        self.client = self._init_openai_client()

    def _init_openai_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        return OpenAI(api_key=  OPENAI_KEY)

    def _find_all_mp4_files(self):
        """查找所有MP4文件"""
        mp4_files = glob.glob(os.path.join(self.output_folder, '*.mp4'))
        if not mp4_files:
            return []
        # 按修改时间排序，最新的在前
        mp4_files.sort(key=os.path.getmtime, reverse=True)
        return [os.path.basename(f) for f in mp4_files]

    def _display_mp4_files(self, mp4_files):
        """显示所有MP4文件供用户选择"""
        print("\n找到以下MP4文件：")
        for i, file in enumerate(mp4_files, 1):
            file_path = os.path.join(self.output_folder, file)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{i}. {file} ({file_size:.1f}MB, 修改时间: {mod_time})")
        print("0. 退出当前步骤")

    def _select_video_file(self):
        """选择视频文件"""
        mp4_files = self._find_all_mp4_files()
        if not mp4_files:
            raise Exception("未找到任何MP4视频文件")
        
        self._display_mp4_files(mp4_files)
        
        while True:
            try:
                choice = input(f"\n请选择要处理的视频文件 (1-{len(mp4_files)}, 0退出): ").strip()
                if choice == '0':
                    raise ValueError("用户选择退出当前步骤")
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(mp4_files):
                    self.video_file = mp4_files[choice_num - 1]
                    self.video_filename = self.video_file
                    print(f"已选择视频文件: {self.video_file}")
                    break
                else:
                    print(f"请输入1到{len(mp4_files)}之间的数字")
            except ValueError as e:
                if "用户选择退出" in str(e):
                    raise e
                print("请输入有效的数字")
            except KeyboardInterrupt:
                raise ValueError("用户选择退出当前步骤")

    def _download_from_google_drive(self, url: str) -> Optional[str]:
        """从Google Drive下载视频"""
        try:
            print("从Google Drive下载视频...")
            output_path = os.path.join(self.output_folder, self.video_filename)
            ydl_opts = {
                'format': 'mp4',
                'outtmpl': output_path,
                'quiet': False,
                'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if os.path.exists(output_path):
                print(f"视频已下载到: {output_path}")
                return output_path
            raise Exception("下载失败")
        except Exception as e:
            print(f"从Google Drive下载视频时出错: {str(e)}")
            traceback.print_exc()
            return None

    def _convert_to_mp3(self, input_file: str, output_file: str) -> bool:
        """将音频文件转换为MP3格式"""
        try:
            # 🚀 优化：检查缓存
            if ENABLE_CACHE and os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024 * 1024)
                if file_size > 0.1:  # 至少100KB
                    print(f"✓ 发现缓存的MP3文件: {output_file} ({file_size:.1f}MB)")
                    print("  跳过转换步骤，直接使用缓存文件")
                    return True
            
            print(f"转换音频文件: {input_file} -> {output_file}")
            
            # 显示文件大小和预计时间
            input_size = os.path.getsize(input_file) / (1024 * 1024)
            print(f"  视频大小: {input_size:.1f}MB")
            print(f"  预计转换时间: {format_time(input_size * 2)}")
            
            start_time = time.time()
            
            # 首先尝试使用pydub
            try:
                audio = AudioSegment.from_file(input_file)
                audio.export(output_file, format="mp3")
                elapsed = time.time() - start_time
                print(f"✓ 使用 pydub 转换成功 (耗时: {format_time(elapsed)})")
                return True
            except Exception as e:
                print(f"✗ 使用 pydub 转换失败，尝试其他方法: {str(e)}")
            
            # 如果pydub失败，尝试使用ffmpeg命令行
            try:
                if ffmpeg_path:
                    cmd = [ffmpeg_path, '-i', input_file, '-vn', '-acodec', 'libmp3lame', output_file]
                    subprocess.run(cmd, check=True, capture_output=True)
                    elapsed = time.time() - start_time
                    print(f"✓ 使用 ffmpeg 转换成功 (耗时: {format_time(elapsed)})")
                    return True
                else:
                    print("✗ 使用 ffmpeg 转换失败: ffmpeg not found")
            except Exception as e:
                print(f"✗ 使用 ffmpeg 转换失败: {str(e)}")
            
            raise Exception("所有转换方法都失败了")
            
        except Exception as e:
            print(f"转换MP3时出错: {str(e)}")
            traceback.print_exc()
            return False

    def _safe_remove_file(self, file_path: str, max_retries: int = 5) -> bool:
        """安全删除文件，带重试机制（解决Windows文件锁定问题）"""
        for attempt in range(max_retries):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # 等待0.5秒后重试
                else:
                    print(f"  ⚠️ 无法删除文件 {file_path}，跳过")
                    return False
        return False

    def _split_audio(self, mp3_path: str) -> List[str]:
        """将大音频文件分割成小片段"""
        try:
            print(f"  正在加载音频文件...")
            audio = AudioSegment.from_mp3(mp3_path)
            total_seconds = len(audio) / 1000
            file_size = os.path.getsize(mp3_path)
            seconds_per_chunk = total_seconds * (MAX_AUDIO_SIZE_MB * 1024 * 1024) / file_size
            
            estimated_chunks = int(total_seconds / seconds_per_chunk) + 1
            print(f"  音频时长: {format_time(total_seconds)}")
            print(f"  预计分割为约 {estimated_chunks} 个片段\n")
            
            chunks = []
            start_time = 0
            chunk_index = 1
            
            while start_time < total_seconds:
                end_time = min(start_time + seconds_per_chunk, total_seconds)
                chunk = audio[start_time*1000:end_time*1000]
                
                chunk_path = os.path.join(self.output_folder, f"{self.chunk_prefix}{chunk_index}.mp3")
                
                # 🔧 修复：导出前先删除旧文件（如果存在）
                if os.path.exists(chunk_path):
                    self._safe_remove_file(chunk_path)
                
                chunk.export(chunk_path, format="mp3")
                
                # 🔧 修复：等待文件完全写入
                time.sleep(0.1)
                
                chunk_size = os.path.getsize(chunk_path) / (1024 * 1024)
                
                if os.path.getsize(chunk_path) > MAX_AUDIO_SIZE_MB * 1024 * 1024:
                    # 🔧 修复：使用安全删除方法
                    self._safe_remove_file(chunk_path)
                    seconds_per_chunk *= 0.8
                    continue
                    
                chunks.append(chunk_path)
                progress = (start_time / total_seconds) * 100
                print(f"  ✓ 创建音频片段 {chunk_index} ({chunk_size:.1f}MB) - 进度: {progress:.0f}%")
                
                start_time = end_time
                chunk_index += 1
                
            return chunks
        except Exception as e:
            print(f"  ✗ 分割音频时出错: {str(e)}")
            traceback.print_exc()
            return []

    def _transcribe_audio(self, audio_path: str, chunk_num: int = 0, total_chunks: int = 1) -> Optional[dict]:
        """转录音频文件"""
        try:
            file_size = os.path.getsize(audio_path) / (1024 * 1024)
            
            if total_chunks > 1:
                print(f"  [{chunk_num}/{total_chunks}] 转录音频块: {os.path.basename(audio_path)} ({file_size:.1f}MB)")
            else:
                print(f"  转录音频文件: {os.path.basename(audio_path)} ({file_size:.1f}MB)")
            
            estimated_time = estimate_transcription_time(file_size)
            print(f"  预计转录时间: {format_time(estimated_time)}")
            
            start_time = time.time()
            
            with open(audio_path, "rb") as audio_file:
                result = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language="en"
                )
            
            elapsed = time.time() - start_time
            print(f"  ✓ 转录完成 (实际耗时: {format_time(elapsed)})")
            
            return result
            
        except Exception as e:
            print(f"  ✗ 转录音频时出错: {str(e)}")
            traceback.print_exc()
            return None

    def _merge_subtitles(self, segments: List[Any], time_offset: float = 0) -> List[dict]:
        """合并字幕片段，添加时间偏移，并确保时间戳不重叠"""
        merged = []
        for i, segment in enumerate(segments):
            # 智能处理两种格式：对象格式和字典格式
            try:
                # 首先尝试对象格式访问
                start_time = segment.start + time_offset
                end_time = segment.end + time_offset
                text = segment.text
            except AttributeError:
                # 如果对象格式失败，尝试字典格式访问
                start_time = segment['start'] + time_offset
                end_time = segment['end'] + time_offset
                text = segment['text']
            
            merged.append({
                'start': start_time,
                'end': end_time,
                'text': text
            })
            
        return merged

    def _transcribe_chunk_with_metadata(self, chunk_info: tuple) -> Optional[tuple]:
        """转录单个音频块（用于并行处理）"""
        chunk_path, chunk_index, total_chunks, time_offset = chunk_info
        try:
            transcript = self._transcribe_audio(chunk_path, chunk_index, total_chunks)
            if transcript:
                # 获取音频时长用于时间偏移计算
                audio_chunk = AudioSegment.from_mp3(chunk_path)
                duration = len(audio_chunk) / 1000
                return (chunk_index, transcript.segments, time_offset, duration)
            return None
        except Exception as e:
            print(f"  ✗ 处理音频块 {chunk_index} 时出错: {str(e)}")
            return None

    def _process_large_audio(self, mp3_path: str) -> List[dict]:
        """处理大型音频文件（并行转录）"""
        print("\n🔄 音频文件过大，进行分割处理...")
        chunks = self._split_audio(mp3_path)
        if not chunks:
            raise Exception("音频分割失败")
        
        print(f"\n📊 已分割为 {len(chunks)} 个音频块")
        
        # 计算每个chunk的时间偏移
        chunk_infos = []
        current_time = 0
        for i, chunk_path in enumerate(chunks, 1):
            audio_chunk = AudioSegment.from_mp3(chunk_path)
            duration = len(audio_chunk) / 1000
            chunk_infos.append((chunk_path, i, len(chunks), current_time))
            current_time += duration
        
        # 🚀 并行转录音频块
        print(f"\n⚡ 开始并行转录（最多 {MAX_PARALLEL_CHUNKS} 个并发）...")
        total_estimated = sum(estimate_transcription_time(os.path.getsize(c[0]) / (1024 * 1024)) for c in chunk_infos)
        print(f"预计总时间（串行）: {format_time(total_estimated)}")
        print(f"预计总时间（并行）: {format_time(total_estimated / min(MAX_PARALLEL_CHUNKS, len(chunks)))}\n")
        
        start_time = time.time()
        results = {}
        
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as executor:
            future_to_chunk = {executor.submit(self._transcribe_chunk_with_metadata, info): info for info in chunk_infos}
            
            completed = 0
            for future in as_completed(future_to_chunk):
                completed += 1
                result = future.result()
                if result:
                    chunk_index, segments, time_offset, duration = result
                    results[chunk_index] = (segments, time_offset)
                    print(f"  ✓ 已完成 {completed}/{len(chunks)} 个音频块")
        
        elapsed = time.time() - start_time
        print(f"\n✓ 所有音频块转录完成！总耗时: {format_time(elapsed)}")
        print(f"  节省时间: {format_time(total_estimated - elapsed)}")
        
        # 按顺序合并所有片段
        all_segments = []
        for i in sorted(results.keys()):
            segments, time_offset = results[i]
            chunk_segments = self._merge_subtitles(segments, time_offset)
            all_segments.extend(chunk_segments)
        
        # 清理临时文件
        print("\n🧹 清理临时文件...")
        for chunk_path, _, _, _ in chunk_infos:
            if os.path.exists(chunk_path):
                self._safe_remove_file(chunk_path)
        
        return all_segments

    def process(self) -> Optional[str]:
        """主处理函数"""
        try:
            mp3_path = os.path.join(self.output_folder, self.audio_filename)
            sbv_path = os.path.join(self.output_folder, self.subtitle_filename)
            
            print("\n" + "="*60)
            print("🎬 Step 1: 提取视频字幕")
            print("="*60)
            
            # 🚀 优化：检查输出文件是否已存在
            if SKIP_IF_OUTPUT_EXISTS and os.path.exists(sbv_path):
                file_size = os.path.getsize(sbv_path) / 1024
                print(f"\n✓ 发现已存在的字幕文件: {sbv_path}")
                print(f"  文件大小: {file_size:.1f}KB")
                
                user_input = input("\n是否跳过处理，直接使用现有文件？(Y/n): ").strip().lower()
                if user_input != 'n':
                    print("✓ 使用现有字幕文件")
                    return sbv_path
                else:
                    print("继续重新处理...")
            
            # 只有在需要处理视频时才选择视频文件
            print("\n📂 第1步：选择视频文件")
            self._select_video_file()
            video_path = os.path.join(self.output_folder, self.video_file)
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"找不到视频文件: {video_path}")
            
            # 转换视频为MP3
            print("\n🎵 第2步：转换视频为MP3音频")
            if not self._convert_to_mp3(video_path, mp3_path):
                raise Exception("视频转换失败")
            
            # 处理音频
            mp3_size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
            print(f"\n🎤 第3步：转录音频为文字")
            print(f"音频文件大小: {mp3_size_mb:.1f}MB")
            
            total_start_time = time.time()
            
            if mp3_size_mb > MAX_AUDIO_SIZE_MB:
                segments = self._process_large_audio(mp3_path)
            else:
                print(f"音频大小适中，直接转录...")
                estimated = estimate_transcription_time(mp3_size_mb)
                print(f"预计转录时间: {format_time(estimated)}\n")
                
                transcript = self._transcribe_audio(mp3_path)
                if not transcript:
                    raise Exception("音频转录失败")
                segments = transcript.segments
            
            total_elapsed = time.time() - total_start_time
            
            # 保存字幕
            print(f"\n💾 第4步：保存字幕文件")
            save_sbv_subtitle(segments, sbv_path)
            
            print("\n" + "="*60)
            print("✅ 处理完成！")
            print("="*60)
            print(f"字幕文件: {sbv_path}")
            print(f"总耗时: {format_time(total_elapsed)}")
            print(f"字幕片段数: {len(segments) if hasattr(segments, '__len__') else 'N/A'}")
            print("="*60 + "\n")
            
            return sbv_path
            
        except ValueError as e:
            if "用户选择退出" in str(e):
                print("\n⚠️  用户取消操作")
                return None
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"\n❌ 处理失败: {str(e)}")
            traceback.print_exc()
            return None

def main():
    try:          
        # 读取配置并处理
        processor = VideoProcessor(DEFAULT_OUTPUT_FOLDER)
        result = processor.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()