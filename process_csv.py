#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理CSV文件：
1. 清洗website列，提取域名格式（xxx.com）
2. 从social_raw列中提取Instagram和Facebook链接
"""

import pandas as pd
import json
import re
from urllib.parse import urlparse, parse_qs


def clean_website(url):
    """
    清洗website列中的URL，提取域名格式（xxx.com）
    
    Args:
        url: 原始URL字符串
        
    Returns:
        清洗后的域名格式，如 xxx.com，如果无法提取则返回空字符串
    """
    if pd.isna(url) or url == '' or url == '[]':
        return ''
    
    url = str(url).strip()
    
    # 处理 /url?q= 格式的URL（Google搜索结果）
    if url.startswith('/url?q=') or '/url?q=' in url:
        # 提取查询参数中的URL
        try:
            parsed = parse_qs(urlparse(url).query)
            if 'q' in parsed and parsed['q']:
                url = parsed['q'][0]
        except Exception:
            pass
    
    # 跳过Google Maps链接和其他Google服务
    if 'google.com/maps' in url.lower() or 'google.com/search' in url.lower():
        return ''
    
    try:
        # 如果URL不包含协议，添加http://以便解析
        if not url.startswith(('http://', 'https://')):
            # 如果已经是域名格式（包含点），添加协议
            if '.' in url and not url.startswith('/'):
                url = 'http://' + url
            else:
                return ''
        
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # 如果没有netloc，尝试从path中提取
        if not domain:
            path_parts = parsed_url.path.split('/')
            if path_parts and '.' in path_parts[0]:
                domain = path_parts[0]
            else:
                return ''
        
        # 移除www.前缀
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # 移除端口号
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # 验证域名格式（至少包含一个点，且不是IP地址）
        if '.' in domain and len(domain) > 0:
            # 简单验证：确保不是纯数字IP地址
            parts = domain.split('.')
            if len(parts) >= 2:
                # 检查是否所有部分都是数字（可能是IP地址）
                if not all(part.isdigit() for part in parts):
                    return domain
        
        return ''
    except Exception as e:
        return ''


def extract_social_links(social_raw):
    """
    从social_raw列中提取Instagram和Facebook链接
    
    Args:
        social_raw: JSON格式的字符串或空值
        
    Returns:
        tuple: (facebook_url, instagram_url)
    """
    facebook_url = ''
    instagram_url = ''
    
    if pd.isna(social_raw) or social_raw == '' or social_raw == '[]':
        return facebook_url, instagram_url
    
    try:
        # 处理字符串格式的JSON
        social_str = str(social_raw).strip()
        
        # 如果字符串为空或只是空列表，返回空值
        if not social_str or social_str == '[]' or social_str == '{}':
            return facebook_url, instagram_url
        
        # 解析JSON字符串
        social_data = json.loads(social_str)
        
        if isinstance(social_data, dict):
            facebook_url = social_data.get('facebook', '')
            instagram_url = social_data.get('instagram', '')
        
        # 确保返回的是字符串，且去除首尾空格
        facebook_url = str(facebook_url).strip() if facebook_url else ''
        instagram_url = str(instagram_url).strip() if instagram_url else ''
        
    except (json.JSONDecodeError, TypeError, AttributeError, ValueError) as e:
        # 如果JSON解析失败，尝试使用正则表达式直接提取
        try:
            social_str = str(social_raw)
            # 尝试提取Facebook链接
            fb_match = re.search(r'"facebook"\s*:\s*"([^"]+)"', social_str)
            if fb_match:
                facebook_url = fb_match.group(1).strip()
            
            # 尝试提取Instagram链接
            ig_match = re.search(r'"instagram"\s*:\s*"([^"]+)"', social_str)
            if ig_match:
                instagram_url = ig_match.group(1).strip()
        except Exception:
            pass
    
    return facebook_url, instagram_url


def main():
    # 读取CSV文件
    input_file = '12.30-master_business_info - Sheet1.csv'
    output_file = '12.30-master_business_info - Sheet1_processed.csv'
    
    print(f'正在读取文件: {input_file}')
    df = pd.read_csv(input_file, encoding='utf-8')
    
    print(f'共读取 {len(df)} 行数据')
    
    # 1. 清洗website列，创建website_clean列
    print('正在清洗website列...')
    df['website_clean'] = df['website'].apply(clean_website)
    
    # 2. 提取social_raw列中的Instagram和Facebook链接
    print('正在提取社交媒体链接...')
    social_links = df['social_raw'].apply(extract_social_links)
    df['facebook_url'] = social_links.apply(lambda x: x[0])
    df['instagram_url'] = social_links.apply(lambda x: x[1])
    
    # 保存处理后的CSV文件
    print(f'正在保存处理后的文件: {output_file}')
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print('处理完成！')
    print(f'\n统计信息:')
    print(f'  - 成功提取域名的记录数: {df["website_clean"].notna().sum()}')
    print(f'  - 成功提取Facebook链接的记录数: {df["facebook_url"].notna().sum()}')
    print(f'  - 成功提取Instagram链接的记录数: {df["instagram_url"].notna().sum()}')
    
    # 显示前几行示例
    print(f'\n前5行处理结果示例:')
    print(df[['business_id', 'name', 'website', 'website_clean', 'facebook_url', 'instagram_url']].head())


if __name__ == '__main__':
    main()

