#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON to CSV Converter
将小红书搜索结果JSON文件转换为CSV格式
"""

import json
import csv
import os
from datetime import datetime

def convert_json_to_csv(json_file_path, csv_file_path=None):
    """
    将JSON文件转换为CSV格式
    
    Args:
        json_file_path (str): JSON文件路径
        csv_file_path (str): CSV输出文件路径，如果为None则自动生成
    
    Returns:
        str: 生成的CSV文件路径
    """
    try:
        # 读取JSON文件
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            print("JSON文件为空或格式错误")
            return None
        
        # 如果没有指定CSV文件路径，则自动生成
        if csv_file_path is None:
            base_name = os.path.splitext(os.path.basename(json_file_path))[0]
            csv_file_path = os.path.join(os.path.dirname(json_file_path), f"{base_name}.csv")
        
        # 获取所有字段名
        all_fields = set()
        for item in data:
            all_fields.update(item.keys())
        
        # 按原始顺序排列字段
        field_order = [
            'note_id', 'type', 'title', 'desc', 'video_url', 'time', 'last_update_time',
            'user_id', 'nickname', 'avatar', 'liked_count', 'collected_count', 
            'comment_count', 'share_count', 'ip_location', 'image_list', 'tag_list',
            'last_modify_ts', 'note_url', 'source_keyword', 'xsec_token'
        ]
        
        # 确保所有字段都在field_order中
        for field in all_fields:
            if field not in field_order:
                field_order.append(field)
        
        # 写入CSV文件
        with open(csv_file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=field_order, extrasaction='ignore')
            
            # 写入表头
            writer.writeheader()
            
            # 写入数据行
            for item in data:
                # 处理时间戳转换为可读格式
                row = item.copy()
                
                # 转换时间戳为可读格式
                if 'time' in row and row['time']:
                    try:
                        row['time'] = datetime.fromtimestamp(row['time'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                if 'last_update_time' in row and row['last_update_time']:
                    try:
                        row['last_update_time'] = datetime.fromtimestamp(row['last_update_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                if 'last_modify_ts' in row and row['last_modify_ts']:
                    try:
                        row['last_modify_ts'] = datetime.fromtimestamp(row['last_modify_ts'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                # 清理文本内容中的换行符和制表符
                for key in ['desc', 'title']:
                    if key in row and row[key]:
                        row[key] = str(row[key]).replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
                
                writer.writerow(row)
        
        print(f"转换完成！CSV文件已保存到: {csv_file_path}")
        print(f"共转换了 {len(data)} 条记录")
        
        return csv_file_path
        
    except FileNotFoundError:
        print(f"错误：找不到文件 {json_file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件格式错误 - {e}")
        return None
    except Exception as e:
        print(f"错误：转换过程中出现异常 - {e}")
        return None

def main():
    """主函数"""
    # 默认JSON文件路径
    json_file = "data/xhs/json/search_contents_2025-09-23.json"
    
    # 检查文件是否存在
    if not os.path.exists(json_file):
        print(f"错误：文件 {json_file} 不存在")
        return
    
    # 转换文件
    csv_file = convert_json_to_csv(json_file)
    
    if csv_file:
        print(f"\n转换成功！")
        print(f"输入文件: {json_file}")
        print(f"输出文件: {csv_file}")
        
        # 显示文件大小信息
        json_size = os.path.getsize(json_file) / 1024 / 1024  # MB
        csv_size = os.path.getsize(csv_file) / 1024 / 1024   # MB
        print(f"JSON文件大小: {json_size:.2f} MB")
        print(f"CSV文件大小: {csv_size:.2f} MB")

if __name__ == "__main__":
    main()
