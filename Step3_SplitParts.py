######################################################################
#  COPYRIGHT 2023-24 
#  Function：分割字幕文件为多个部分
######################################################################
import os
import traceback
from typing import List, Dict, Optional
from dataclasses import dataclass
from common_utils import (
    SubtitleSegment, parse_time, format_time,
    parse_sbv_file, save_sbv_file, 
)

#CONFIG_FILENAME = "configuration.txt"
DEFAULT_OUTPUT_FOLDER = "DataFiles"  # Set this to a specific folder name if you want to override the date-based folder

# 文件名配置
MERGED_ENGLISH_SBV_FILE = "step2_merged_en.sbv"  # 合并后的英文字幕文件名（来自Step2的输出）
PART_EN_SUFFIX = "-Step3.sbv"  # 英文字幕文件后缀
PART_PREFIX = ""  # Part文件前缀（因为self.parts已包含完整Part名称）

@dataclass
class PartInfo:
    """Part信息类"""
    name: str
    duration: str = ""  # MM:SS 格式

class SubtitleSplitter:
    def __init__(self, parts: List[str], output_folder: str):
        self.output_folder = output_folder if output_folder and output_folder.strip() else '.'
        
        # 确保输出目录存在
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"创建输出目录: {self.output_folder}")
        
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
        self.merged_en_file = MERGED_ENGLISH_SBV_FILE
        self.part_en_suffix = PART_EN_SUFFIX
        self.part_prefix = PART_PREFIX

    def _split_subtitles(self, segments: List[SubtitleSegment]) -> Dict[str, List[SubtitleSegment]]:
        """将字幕平均分配给每个part"""
        if not segments:
            return {}
            
        # 计算总时长
        total_duration = parse_time(segments[-1].end_time)
        print(f"总时长: {self._format_duration(total_duration)}")
        
        # 如果只有一个part，直接复制所有字幕
        if len(self.parts) == 1:
            print("检测到只有一个Part，直接复制所有字幕")
            result = {}
            result[self.parts[0]] = segments.copy()
            return result
        
        # 计算每个part的时长
        duration_per_part = total_duration / len(self.parts)
        print(f"每个Part的时长: {self._format_duration(duration_per_part)}")
        
        # 分割字幕
        result = {}
        current_time = 0
        
        for i, part_name in enumerate(self.parts):
            end_time = current_time + duration_per_part
            print(f"\n处理 {part_name}")
            print(f"时间范围: {self._format_duration(current_time)} - {self._format_duration(end_time)}")
            
            # 收集当前时间段内的字幕
            part_segments = []
            for segment in segments:
                segment_start = parse_time(segment.start_time)
                # 对于最后一个part，包含所有剩余的字幕
                if i == len(self.parts) - 1:
                    if current_time <= segment_start:
                        part_segments.append(segment)
                else:
                    if current_time <= segment_start < end_time:
                        part_segments.append(segment)
            
            result[part_name] = part_segments
            print(f"收集到 {len(part_segments)} 个字幕片段")
            current_time = end_time
        
        # 将result中的每一个part的结束时间减少0.05秒
        for part_segments in result.values():
            for segment in part_segments:
                segment.end_time = format_time(parse_time(segment.end_time) - 0.05)

        return result

    def _format_duration(self, seconds: float) -> str:
        """将秒数转换为MM:SS格式"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def process(self) -> bool:
        """主处理函数"""
        try:
            if not os.path.exists(self.output_folder):
                raise FileNotFoundError(f'文件夹不存在: {self.output_folder}')
            

            
            input_file = os.path.join(self.output_folder, self.merged_en_file)
            if not os.path.exists(input_file):
                raise FileNotFoundError(f'输入文件不存在: {input_file}')
            print(f"\n读取文件: {input_file}")
            segments = parse_sbv_file(input_file)
            print(f"读取到 {len(segments)} 个字幕片段")


            
            # 执行分割处理
            split_results = self._split_subtitles(segments)
            for part_name, part_segments in split_results.items():
                # 将part1转换为Part1格式
                part_name_capitalized = part_name.capitalize()
                output_file = os.path.join(self.output_folder, f"{part_name_capitalized}{self.part_en_suffix}")
                save_sbv_file(part_segments, output_file)
                print(f"已保存: {output_file}")
            return True
        except Exception as e:
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return False

def main():
    try:
        # Example usage
        parts = [f"part{i}" for i in range(1, 11)]  # Create 10 parts
        splitter = SubtitleSplitter(parts, "output")
        result = splitter.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()