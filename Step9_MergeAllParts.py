######################################################################
#  COPYRIGHT 2023-24 
#  合并所有Part文件为PartAll文件
######################################################################
import os
import re
import glob
from typing import List, Tuple, Optional
from datetime import datetime

class PartAllMerger:
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")
    
    def _parse_timestamp(self, timestamp_str: str) -> float:
        """解析时间戳字符串为秒数"""
        # 格式: HH:MM:SS.mmm
        parts = timestamp_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
        
        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
        return total_seconds
    
    def _parse_sbv_content(self, content: str) -> List[Tuple[float, float, str]]:
        """解析SBV文件内容，返回(开始时间, 结束时间, 文本)的列表"""
        segments = []
        lines = content.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # 检查是否是时间戳行
            if re.match(r'\d{2}:\d{2}:\d{2}\.\d{3},\d{2}:\d{2}:\d{2}\.\d{3}', line):
                try:
                    start_time_str, end_time_str = line.split(',')
                    start_time = self._parse_timestamp(start_time_str)
                    end_time = self._parse_timestamp(end_time_str)
                    
                    # 收集文本内容
                    text_lines = []
                    i += 1
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i].strip())
                        i += 1
                    
                    if text_lines:
                        text = '\n'.join(text_lines)
                        segments.append((start_time, end_time, text))
                except Exception as e:
                    print(f"解析时间戳行时出错: {line} -> {e}")
                    i += 1
            else:
                i += 1
        
        return segments
    
    def _find_video_filename(self) -> Optional[str]:
        """查找DataFiles目录中的视频文件名（.mp4），返回不含扩展名的文件名"""
        try:
            # 查找所有 .mp4 文件
            mp4_files = glob.glob(os.path.join(self.output_folder, "*.mp4"))
            
            if not mp4_files:
                return None
            
            # 如果找到多个，使用第一个（或者可以返回最新的）
            # 按修改时间排序，使用最新的
            mp4_files.sort(key=os.path.getmtime, reverse=True)
            video_file = mp4_files[0]
            
            # 返回不含扩展名的文件名
            video_basename = os.path.basename(video_file)
            video_name_without_ext = os.path.splitext(video_basename)[0]
            return video_name_without_ext
        except Exception as e:
            print(f"查找视频文件时出错: {e}")
            return None
    
    def _generate_output_filename(self) -> str:
        """生成输出文件名
        
        Returns:
            生成的文件名，格式：{视频文件名}-英文直译意译-{日期}.sbv
        """
        # 获取视频文件名
        video_name = self._find_video_filename()
        
        # 获取当前日期（格式：YY-MM-DD）
        today = datetime.now()
        date_str = today.strftime("%y-%m-%d")
        
        # 构建文件名
        if video_name:
            filename = f"{video_name}-英文直译意译-{date_str}.sbv"
        else:
            filename = f"英文直译意译-{date_str}.sbv"
        
        return filename
    
    def _find_part_files(self, pattern: str) -> List[str]:
        """查找匹配模式的Part文件，排除合并结果文件"""
        files = glob.glob(os.path.join(self.output_folder, pattern))
        
        # 排除合并结果文件
        excluded_files = ["PartAll-Step4-All.sbv", "PartAll-Step5-All.sbv"]
        files = [f for f in files if os.path.basename(f) not in excluded_files]
        
        # 按Part编号排序，添加错误处理
        def extract_part_number(filename):
            match = re.search(r'Part(\d+)', filename)
            if match:
                return int(match.group(1))
            else:
                print(f"警告: 无法从文件名中提取Part编号: {filename}")
                return 0  # 返回0作为默认值，这样文件会被排在前面
        
        files.sort(key=extract_part_number)
        return files
    
    def _merge_sbv_files(self, input_files: List[str], output_file: str) -> bool:
        """合并多个SBV文件为一个文件"""
        try:
            all_segments = []
            
            # 读取所有文件的片段
            for file_path in input_files:
                print(f"    读取文件: {os.path.basename(file_path)}")
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    segments = self._parse_sbv_content(content)
                    all_segments.extend(segments)
                    print(f"        找到 {len(segments)} 个片段")
                    
                except Exception as e:
                    print(f"        读取文件失败: {e}")
                    continue
            
            if not all_segments:
                print(f"    没有找到任何有效片段")
                return False
            
            # 按开始时间排序
            all_segments.sort(key=lambda x: x[0])
            
            # 写入合并后的文件
            with open(output_file, 'w', encoding='utf-8') as f:
                for i, (start_time, end_time, text) in enumerate(all_segments):
                    # 转换回时间戳格式
                    start_hours = int(start_time // 3600)
                    start_minutes = int((start_time % 3600) // 60)
                    start_seconds = int(start_time % 60)
                    start_milliseconds = int((start_time % 1) * 1000)
                    
                    end_hours = int(end_time // 3600)
                    end_minutes = int((end_time % 3600) // 60)
                    end_seconds = int(end_time % 60)
                    end_milliseconds = int((end_time % 1) * 1000)
                    
                    start_timestamp = f"{start_hours:02d}:{start_minutes:02d}:{start_seconds:02d}.{start_milliseconds:03d}"
                    end_timestamp = f"{end_hours:02d}:{end_minutes:02d}:{end_seconds:02d}.{end_milliseconds:03d}"
                    
                    f.write(f"{start_timestamp},{end_timestamp}\n")
                    f.write(f"{text}\n")
                    f.write("\n")
            
            print(f"    成功合并 {len(all_segments)} 个片段到: {os.path.basename(output_file)}")
            return True
            
        except Exception as e:
            print(f"    合并文件时出错: {e}")
            return False
    
    def process(self) -> bool:
        """主处理函数"""
        try:
            print("开始合并所有Part文件...")
            
            # 查找Step5-all文件
            step5_pattern = "Part*-Step5-all.sbv"
            step5_files = self._find_part_files(step5_pattern)
            
            if step5_files:
                print(f"找到 {len(step5_files)} 个Step5-all文件:")
                for file in step5_files:
                    print(f"  - {os.path.basename(file)}")
                
                # 生成输出文件名
                output_filename = self._generate_output_filename()
                output_file = os.path.join(self.output_folder, output_filename)
                
                if self._merge_sbv_files(step5_files, output_file):
                    print(f"✓ 文件合并完成: {output_filename}")
                    return True
                else:
                    print("✗ 文件合并失败")
                    return False
            else:
                print("未找到任何Step5-all文件")
                return False
            
        except Exception as e:
            print(f"处理失败: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    try:
        output_folder = '.'
        merger = PartAllMerger(output_folder)
        result = merger.process()
        
        if result:
            print("\n✓ 所有Part文件合并完成")
        else:
            print("\n✗ Part文件合并失败")
            
    except Exception as e:
        print(f"程序执行出错: {e}")

if __name__ == "__main__":
    main()
