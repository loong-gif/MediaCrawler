#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片下载器
从CSV文件中提取image_list列的图片链接并下载
"""

import csv
import os
import urllib.request
import urllib.error
import time
from urllib.parse import urlparse
from pathlib import Path
import re

class ImageDownloader:
    def __init__(self, csv_file_path, download_dir="downloaded_images"):
        """
        初始化图片下载器
        
        Args:
            csv_file_path (str): CSV文件路径
            download_dir (str): 图片下载目录
        """
        self.csv_file_path = csv_file_path
        self.download_dir = Path(download_dir)
        
        # 设置请求头，模拟浏览器访问
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.xiaohongshu.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 创建下载目录
        self.download_dir.mkdir(exist_ok=True)
        
        # 统计信息
        self.total_images = 0
        self.downloaded_images = 0
        self.failed_images = 0
        self.skipped_images = 0
    
    def extract_image_urls(self, image_list_str):
        """
        从image_list字符串中提取图片URL列表
        
        Args:
            image_list_str (str): image_list列的字符串
            
        Returns:
            list: 图片URL列表
        """
        if not image_list_str or image_list_str.strip() == '':
            return []
        
        # 按逗号分割URL
        urls = [url.strip() for url in image_list_str.split(',')]
        
        # 过滤掉空字符串
        urls = [url for url in urls if url]
        
        return urls
    
    def get_filename_from_url(self, url, note_id, index):
        """
        从URL生成文件名
        
        Args:
            url (str): 图片URL
            note_id (str): 笔记ID
            index (int): 图片索引
            
        Returns:
            str: 文件名
        """
        parsed_url = urlparse(url)
        
        # 尝试从URL中提取原始文件名
        path_parts = parsed_url.path.split('/')
        if path_parts:
            filename = path_parts[-1]
            # 移除查询参数部分
            if '!' in filename:
                filename = filename.split('!')[0]
        else:
            # 如果没有文件名，使用默认格式
            filename = f"image_{index}.jpg"
        
        # 确保文件名有扩展名
        if '.' not in filename:
            filename += '.jpg'
        
        # 使用note_id作为前缀，避免文件名冲突
        filename = f"{note_id}_{index}_{filename}"
        
        return filename
    
    def download_image(self, url, filepath):
        """
        下载单个图片
        
        Args:
            url (str): 图片URL
            filepath (Path): 保存路径
            
        Returns:
            bool: 下载是否成功
        """
        try:
            # 创建请求对象
            req = urllib.request.Request(url, headers=self.headers)
            
            # 打开URL并下载
            with urllib.request.urlopen(req, timeout=30) as response:
                # 检查内容类型是否为图片
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    print(f"警告: {url} 不是图片文件 (content-type: {content_type})")
                    return False
                
                # 读取数据并写入文件
                data = response.read()
                with open(filepath, 'wb') as f:
                    f.write(data)
            
            return True
            
        except urllib.error.HTTPError as e:
            print(f"HTTP错误 {url}: {e}")
            return False
        except urllib.error.URLError as e:
            print(f"URL错误 {url}: {e}")
            return False
        except Exception as e:
            print(f"下载失败 {url}: {e}")
            return False
    
    def process_csv(self):
        """
        处理CSV文件并下载图片
        """
        print(f"开始处理CSV文件: {self.csv_file_path}")
        print(f"图片将保存到: {self.download_dir.absolute()}")
        
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row_index, row in enumerate(reader, 1):
                    note_id = row.get('note_id', f'row_{row_index}')
                    image_list_str = row.get('image_list', '')
                    
                    if not image_list_str:
                        continue
                    
                    # 提取图片URL
                    image_urls = self.extract_image_urls(image_list_str)
                    
                    if not image_urls:
                        continue
                    
                    print(f"\n处理笔记 {note_id} ({row_index}/{self.get_total_rows()})")
                    print(f"发现 {len(image_urls)} 张图片")
                    
                    # 下载每张图片到主目录
                    for img_index, url in enumerate(image_urls, 1):
                        self.total_images += 1
                        
                        # 生成文件名
                        filename = self.get_filename_from_url(url, note_id, img_index)
                        filepath = self.download_dir / filename
                        
                        # 检查文件是否已存在
                        if filepath.exists():
                            print(f"  跳过已存在的图片: {filename}")
                            self.skipped_images += 1
                            continue
                        
                        print(f"  下载图片 {img_index}/{len(image_urls)}: {filename}")
                        
                        # 下载图片
                        if self.download_image(url, filepath):
                            self.downloaded_images += 1
                            print(f"    ✓ 下载成功")
                        else:
                            self.failed_images += 1
                            print(f"    ✗ 下载失败")
                        
                        # 添加延迟，避免请求过于频繁
                        time.sleep(0.5)
        
        except FileNotFoundError:
            print(f"错误: 找不到文件 {self.csv_file_path}")
        except Exception as e:
            print(f"错误: 处理CSV文件时出现异常 - {e}")
    
    def get_total_rows(self):
        """获取CSV文件总行数"""
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
                return sum(1 for row in csvfile) - 1  # 减去表头行
        except:
            return 0
    
    def print_summary(self):
        """打印下载统计信息"""
        print("\n" + "="*50)
        print("下载完成统计:")
        print(f"总图片数: {self.total_images}")
        print(f"成功下载: {self.downloaded_images}")
        print(f"跳过文件: {self.skipped_images}")
        print(f"下载失败: {self.failed_images}")
        print(f"成功率: {(self.downloaded_images/self.total_images*100):.1f}%" if self.total_images > 0 else "0%")
        print("="*50)

def main():
    """主函数"""
    # CSV文件路径
    csv_file = "data/xhs/csv/creator_contents_2025-09-23.csv"
    
    # 检查文件是否存在
    if not os.path.exists(csv_file):
        print(f"错误: 文件 {csv_file} 不存在")
        return
    
    # 创建下载器并开始下载
    downloader = ImageDownloader(csv_file, "downloaded_images")
    downloader.process_csv()
    downloader.print_summary()

if __name__ == "__main__":
    main()
