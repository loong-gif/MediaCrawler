#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版图片下载器
从CSV文件中提取image_list列的图片链接并下载
"""

import csv
import os
import urllib.request
import urllib.error
import time
from urllib.parse import urlparse
from pathlib import Path

def download_images_from_csv(csv_file_path, download_dir="downloaded_images"):
    """
    从CSV文件下载图片
    
    Args:
        csv_file_path (str): CSV文件路径
        download_dir (str): 下载目录
    """
    print(f"开始处理CSV文件: {csv_file_path}")
    
    # 创建下载目录
    download_path = Path(download_dir)
    download_path.mkdir(exist_ok=True)
    print(f"图片将保存到: {download_path.absolute()}")
    
    # 设置请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.xiaohongshu.com/',
    }
    
    total_images = 0
    downloaded_images = 0
    failed_images = 0
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row_index, row in enumerate(reader, 1):
                note_id = row.get('note_id', f'row_{row_index}')
                image_list_str = row.get('image_list', '')
                
                if not image_list_str:
                    continue
                
                # 提取图片URL
                image_urls = [url.strip() for url in image_list_str.split(',') if url.strip()]
                
                if not image_urls:
                    continue
                
                print(f"\n处理笔记 {note_id} (第{row_index}行)")
                print(f"发现 {len(image_urls)} 张图片")
                
                # 下载每张图片
                for img_index, url in enumerate(image_urls, 1):
                    total_images += 1
                    
                    # 生成文件名
                    parsed_url = urlparse(url)
                    filename = parsed_url.path.split('/')[-1]
                    if '!' in filename:
                        filename = filename.split('!')[0]
                    if '.' not in filename:
                        filename += '.jpg'
                    
                    # 使用note_id作为前缀
                    filename = f"{note_id}_{img_index}_{filename}"
                    filepath = download_path / filename
                    
                    # 检查文件是否已存在
                    if filepath.exists():
                        print(f"  跳过已存在的图片: {filename}")
                        continue
                    
                    print(f"  下载图片 {img_index}/{len(image_urls)}: {filename}")
                    
                    try:
                        # 创建请求并下载
                        req = urllib.request.Request(url, headers=headers)
                        with urllib.request.urlopen(req, timeout=30) as response:
                            data = response.read()
                            with open(filepath, 'wb') as f:
                                f.write(data)
                        
                        downloaded_images += 1
                        print(f"    ✓ 下载成功")
                        
                    except Exception as e:
                        failed_images += 1
                        print(f"    ✗ 下载失败: {e}")
                    
                    # 添加延迟
                    time.sleep(0.5)
    
    except FileNotFoundError:
        print(f"错误: 找不到文件 {csv_file_path}")
        return
    except Exception as e:
        print(f"错误: 处理CSV文件时出现异常 - {e}")
        return
    
    # 打印统计信息
    print("\n" + "="*50)
    print("下载完成统计:")
    print(f"总图片数: {total_images}")
    print(f"成功下载: {downloaded_images}")
    print(f"下载失败: {failed_images}")
    if total_images > 0:
        print(f"成功率: {(downloaded_images/total_images*100):.1f}%")
    print("="*50)

def main():
    """主函数"""
    csv_file = "data/xhs/csv/creator_contents_2025-09-23.csv"
    
    if not os.path.exists(csv_file):
        print(f"错误: 文件 {csv_file} 不存在")
        return
    
    download_images_from_csv(csv_file, "downloaded_images")

if __name__ == "__main__":
    main()

