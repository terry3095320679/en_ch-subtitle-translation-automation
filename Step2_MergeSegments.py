######################################################################
#  COPYRIGHT 2023-24 
#  Function：合并英文字幕片段，优化时间戳
######################################################################
import os
import traceback
from typing import List, Dict
from common_utils import (
    SubtitleSegment, is_sentence_end,
    parse_sbv_file, save_sbv_file, 
    parse_time, format_time, get_output_folder
)

DEFAULT_OUTPUT_FOLDER = "DataFiles"  # Set this to a specific folder name if you want to override the date-based folder
SPLIT_SEGMENTS = 5  # 分割数量配置

# 文件名配置
ENGLISH_SBV_FILE = "step1_video_en.sbv"  # 英文字幕文件名（来自Step1的输出）
MERGED_ENGLISH_SBV_FILE = "step2_merged_en.sbv"  # 合并后的英文字幕文件名

class SubtitleMerger:
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        
        # 确保输出目录存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出目录: {output_folder}")
        
        # 使用常量定义的文件名设置
        self.english_sbv_file = ENGLISH_SBV_FILE
        self.merged_english_sbv_file = MERGED_ENGLISH_SBV_FILE

    def _split_at_sentence_end(self, text: str) -> List[str]:
        """在句子结束标点符号处分割文本"""
        sentences = []
        current = ""
        
        words = text.split()
        for word in words:
            current += word + " "
            if is_sentence_end(current.strip()):
                sentences.append(current.strip())
                current = ""
        
        if current.strip():
            sentences.append(current.strip())
        
        return sentences

    def _split_segment_by_sentences(self, segment: SubtitleSegment) -> List[SubtitleSegment]:
        """将一个字幕片段按句子分割"""
        sentences = self._split_at_sentence_end(segment.text)
        if len(sentences) <= 1:
            return [segment]
        
        split_count = min(len(sentences), SPLIT_SEGMENTS)
        
        if split_count == 2:
            first_sentence = sentences[0]
            remaining_sentences = ' '.join(sentences[1:])
            text_parts = [first_sentence, remaining_sentences]
        else:
            text_parts = sentences[:split_count-1]
            text_parts.append(' '.join(sentences[split_count-1:]))
        
        total_duration = parse_time(segment.end_time) - parse_time(segment.start_time)
        total_length = sum(len(part) for part in text_parts)
        
        new_segments = []
        current_time = parse_time(segment.start_time)
        
        for text_part in text_parts:
            ratio = len(text_part) / total_length
            duration = total_duration * ratio
            end_time = current_time + duration
            
            new_segments.append(SubtitleSegment(
                start_time=format_time(current_time),
                end_time=format_time(end_time),
                text=text_part
            ))
            current_time = end_time
        
        return new_segments

    def _should_merge_segments(self, prev_segment: SubtitleSegment, next_segment: SubtitleSegment) -> bool:
        """判断两个片段是否应该合并
        只有当前一个片段不是完整句子时才合并"""
        prev_text = prev_segment.text.strip()
        return not is_sentence_end(prev_text)
    

    def _resplit_segments(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """重新分割所有字幕片段"""
        resplit = []
        for segment in segments:
            split_segments = self._split_segment_by_sentences(segment)
            resplit.extend(split_segments)
        return resplit

    def _merge_segments(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """合并字幕片段"""
        if not segments:
            return segments
        
        segments = self._resplit_segments(segments)
        merged = []
        current = segments[0]
        
        for next_seg in segments[1:]:
            if self._should_merge_segments(current, next_seg):
                current.end_time = next_seg.end_time
                current.text = f"{current.text} {next_seg.text}"
            else:
                merged.append(current)
                current = next_seg
        
        merged.append(current)
        return merged

    def process(self) -> bool:
        """主处理函数"""
        try:
            output_file = os.path.join(self.output_folder, self.merged_english_sbv_file)
            if not all([self.output_folder, self.english_sbv_file, self.merged_english_sbv_file]):
                raise ValueError("配置文件缺少必要的配置项")
            input_file = os.path.join(self.output_folder, self.english_sbv_file)
            print(f"输入字幕: {input_file}")
            print(f"输出字幕: {output_file}")
            
            segments = parse_sbv_file(input_file)
            print(f"原始片段数: {len(segments)}")
            
            merged_segments = self._merge_segments(segments)
            print(f"合并后片段数: {len(merged_segments)}")

            # 需要再次检查每一个merged_segments中的segment,确保其结束时间比下一个片段的开始时间小100毫秒
            #for i in range(len(merged_segments) - 1):
            #    # 将字符串时间转换为浮点数进行比较
            #    current_end = parse_time(merged_segments[i].end_time)
            #    next_start = parse_time(merged_segments[i + 1].start_time)
            #    if current_end >= next_start:
            #    if current_end >= next_start:
            #        # 调整结束时间并转换回字符串格式
            #        adjusted_end = next_start - 0.1
            #        if adjusted_end > parse_time(merged_segments[i].start_time):  # 确保结束时间大于开始时间
            #            merged_segments[i].end_time = format_time(adjusted_end)
            
            save_sbv_file(merged_segments, output_file)
            print(f"已保存到: {output_file}")
            
            return True
            
        except Exception as e:
            print(f"处理失败: {str(e)}")
            traceback.print_exc()
            return False

def main():
    try:
        output_folder = get_output_folder(DEFAULT_OUTPUT_FOLDER)
        merger = SubtitleMerger(output_folder)
        result = merger.process()
        
        print("处理完成" if result else "处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()