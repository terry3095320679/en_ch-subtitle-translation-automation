######################################################################
#  COPYRIGHT 2023-24 
#  将老数据文件移到OldFiles目录
######################################################################
import os
import glob
import shutil
from typing import List

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

class OldFilesMover:
    def __init__(self, output_folder: str = '.'):
        self.output_folder = output_folder
        
    def _find_old_files(self) -> List[str]:
        """查找需要移动的文件"""
        old_files = []
        target_dir = os.path.join(self.output_folder, "OldFiles")
        
        for dirpath, dirnames, filenames in os.walk(self.output_folder):
            # 跳过 OldFiles 目录本身
            dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) != target_dir]
            
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                # 确保不移动 OldFiles 目录里的文件
                if not file_path.startswith(os.path.join(target_dir, '')):
                    old_files.append(file_path)
        
        return old_files
    
    def _move_files_to_oldfiles(self, old_files: List[str]) -> int:
        """将文件移动到OldFiles目录"""
        old_dir = os.path.join(self.output_folder, "OldFiles")
        
        # 创建OldFiles目录
        if not os.path.exists(old_dir):
            os.makedirs(old_dir)
            print(f"创建目录: {old_dir}")
        
        # 移动文件
        moved_count = 0
        for file_path in old_files:
            try:
                # 计算相对路径，保留原始层级结构
                rel_path = os.path.relpath(file_path, self.output_folder)
                dest_path = os.path.join(old_dir, rel_path)
                dest_dir = os.path.dirname(dest_path)

                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                
                # 如果目标文件已存在，添加时间戳
                if os.path.exists(dest_path):
                    import time
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    name, ext = os.path.splitext(os.path.basename(dest_path))
                    new_name = f"{name}_{timestamp}{ext}"
                    dest_path = os.path.join(dest_dir, new_name)
                
                shutil.move(file_path, dest_path)
                print(f"已移动: {os.path.relpath(file_path, self.output_folder)} -> OldFiles/{os.path.relpath(dest_path, old_dir)}")
                moved_count += 1
            except Exception as e:
                print(f"移动文件 {os.path.basename(file_path)} 时出错: {e}")
        
        return moved_count
    
    def process(self) -> bool:
        """主处理函数"""
        try:
            print("\n=== 步骤10: 将老数据文件移到OldFiles ===")
            
            # 查找老文件
            old_files = self._find_old_files()
            
            if not old_files:
                print("未发现任何老数据文件。")
                return True
            
            # 显示找到的文件
            print(f"\n发现以下 {len(old_files)} 个老数据文件:")
            for file_path in old_files:
                print(f"  - {os.path.basename(file_path)}")
            
            # 询问用户是否移动
            print(f"\n是否希望将这些文件移到 OldFiles 目录中？(Y/n):")
            print("(输入X退出当前步骤)")
            choice = input().strip()
            
            # 处理中文输入模式下的英文字符识别
            choice_clean = clean_input_for_comparison(choice)
            if choice_clean == 'x':
                print("用户选择退出步骤10，返回主菜单。")
                return None
            elif choice_clean in ('y', 'yes', ''):
                # 移动文件
                moved_count = self._move_files_to_oldfiles(old_files)
                print(f"\n✓ 共移动了 {moved_count} 个文件到 OldFiles 目录")
                return True
            else:
                print("保留原有文件，返回主菜单。")
                return True
                
        except Exception as e:
            print(f"处理失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def main():
    try:
        mover = OldFilesMover()
        result = mover.process()
        
        if result is None:
            print("用户选择退出。")
        elif result:
            print("处理完成")
        else:
            print("处理失败")
            
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
