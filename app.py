import os
import re
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from flask import Flask, send_file
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
FILE_PATH = 'ids.txt'

def scrape_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    current_year = now.year

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 开始执行抓取任务...")
    
    js_url = 'https://im-imgs-bucket.oss-accelerate.aliyuncs.com/index.js?t_5'
    try:
        response = requests.get(js_url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求 JS 失败: {e}")
        return

    html_snippets = re.findall(r"document\.write\('(.*?)'\);", response.text)
    html_content = "".join(html_snippets)
    soup = BeautifulSoup(html_content, 'html.parser')

    target_ids = set()
    match_lists = soup.find_all('ul', class_='item play')
    
    for match in match_lists:
        time_li = match.find('li', class_='lab_time')
        if not time_li:
            continue
        
        time_str = time_li.text.strip()
        try:
            match_time = datetime.strptime(f"{current_year}-{time_str}", "%Y-%m-%d %H:%M")
            match_time = tz.localize(match_time)
            
            if match_time > now + timedelta(days=300):
                match_time = match_time.replace(year=current_year - 1)
            elif match_time < now - timedelta(days=300):
                match_time = match_time.replace(year=current_year + 1)
                
        except ValueError:
            continue

        time_diff = abs((match_time - now).total_seconds()) / 3600
        if time_diff <= 3:
            links = match.find_all('a', href=re.compile(r'play\.sportsteam368\.com'))
            for link in links:
                match_url = link.get('href')
                
                try:
                    match_res = requests.get(match_url, headers=headers, timeout=10)
                    match_res.raise_for_status()
                    match_soup = BeautifulSoup(match_res.text, 'html.parser')
                    
                    hd_links = match_soup.find_all('a', text=re.compile(r'高清直播'))
                    for hd in hd_links:
                        data_play = hd.get('data-play')
                        if data_play:
                            play_url = f"http://play.sportsteam368.com{data_play}"
                            play_res = requests.get(play_url, headers=headers, timeout=10)
                            id_match = re.search(r'paps\.html\?id=([A-Za-z0-9+/=]+)', play_res.text)
                            if id_match:
                                target_ids.add(id_match.group(1))
                except Exception as e:
                    print(f"解析失败 {match_url}: {e}")

    # 将结果写入文件
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        for item in target_ids:
            f.write(item + '\n')
    
    print(f"抓取完成！共提取 {len(target_ids)} 个 ID。")

# 配置并启动每 30 分钟一次的定时任务
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(func=scrape_task, trigger="interval", minutes=30, id='scrape_job', replace_existing=True)
scheduler.start()

# 启动时先执行一次，以免前 30 分钟没有数据
scrape_task()

@app.route('/')
def get_ids():
    """访问主页时，返回 txt 文件"""
    if os.path.exists(FILE_PATH):
        return send_file(FILE_PATH, mimetype='text/plain')
    return "抓取任务正在进行中或无匹配数据，请稍后再刷新。", 404

if __name__ == "__main__":
    # 绑定 0.0.0.0 和 8080 端口，适配容器环境
    app.run(host="0.0.0.0", port=8080)
