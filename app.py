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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://play.sportsteam368.com/'
    }

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 开始执行抓取任务...")
    
    js_url = 'https://im-imgs-bucket.oss-accelerate.aliyuncs.com/index.js?t_5'
    try:
        response = requests.get(js_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        response.raise_for_status()
    except Exception as e:
        print(f"❌ 请求主 JS 失败: {e}")
        return

    html_snippets = re.findall(r"document\.write\('(.*?)'\);", response.text)
    html_content = "".join(html_snippets)
    soup = BeautifulSoup(html_content, 'html.parser')

    match_lists = soup.select('ul.item.play')
    print(f"📊 成功解析 JS 文件，共找到 {len(match_lists)} 场比赛信息。")

    target_ids = set()
    
    for match in match_lists:
        time_li = match.find('li', class_='lab_time')
        if not time_li:
            continue
        
        time_str = time_li.get_text(strip=True)
        try:
            match_time_naive = datetime.strptime(f"{current_year}-{time_str}", "%Y-%m-%d %H:%M")
            match_time = tz.localize(match_time_naive)
            
            if match_time > now + timedelta(days=300):
                match_time = tz.localize(match_time_naive.replace(year=current_year - 1))
            elif match_time < now - timedelta(days=300):
                match_time = tz.localize(match_time_naive.replace(year=current_year + 1))
        except ValueError:
            continue

        time_diff = (match_time - now).total_seconds() / 3600
        
        # 筛选前后 3 小时内的比赛
        if -3 <= time_diff <= 3:
            print(f"🕒 找到符合时间的比赛: {time_str}")
            links = match.find_all('a', href=re.compile(r'play\.sportsteam368\.com'))
            
            for link in links:
                match_url = link.get('href')
                
                try:
                    match_res = requests.get(match_url, headers=headers, timeout=10)
                    match_res.encoding = 'utf-8'
                    match_soup = BeautifulSoup(match_res.text, 'html.parser')
                    
                    hd_links = [a for a in match_soup.find_all('a') if '高清直播' in a.get_text()]

                    for hd in hd_links:
                        data_play = hd.get('data-play')
                        if data_play:
                            play_url = f"http://play.sportsteam368.com{data_play}"
                            
                            play_headers = headers.copy()
                            play_headers['Referer'] = match_url
                            
                            play_res = requests.get(play_url, headers=play_headers, timeout=10)
                            play_res.encoding = 'utf-8'
                            
                            # 【核心修改区】：同时兼容新旧两种数据下发规则！
                            # 1. 优先尝试提取新的变量 var encodedStr = '...'
                            id_match_new = re.search(r"var\s+encodedStr\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]", play_res.text)
                            # 2. 备选尝试旧版 paps.html?id=...
                            id_match_old = re.search(r'paps\.html\?id=([A-Za-z0-9+/=]+)', play_res.text)
                            
                            if id_match_new:
                                extracted_id = id_match_new.group(1)
                                target_ids.add(extracted_id)
                                print(f"   ✅ [新结构] 成功提取 ID: {extracted_id[:20]}...")
                            elif id_match_old:
                                extracted_id = id_match_old.group(1)
                                target_ids.add(extracted_id)
                                print(f"   ✅ [旧结构] 成功提取 ID: {extracted_id[:20]}...")
                            else:
                                print(f"   ❌ 该源既不符合新结构也不符合旧结构。URL: {play_url}")

                except Exception as e:
                    print(f"   ❌ 请求页面时发生异常: {e}")

    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        for item in target_ids:
            f.write(item + '\n')
    
    print(f"🎉 抓取任务完成！共提取 {len(target_ids)} 个不重复的 ID。")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(func=scrape_task, trigger="interval", minutes=30, id='scrape_job', replace_existing=True)
scheduler.start()

# 启动时先执行一次
scrape_task()

@app.route('/')
def get_ids():
    if os.path.exists(FILE_PATH) and os.path.getsize(FILE_PATH) > 0:
        return send_file(FILE_PATH, mimetype='text/plain')
    return "✅ 抓取运行完成。但未提取到ID（可能当前前后3小时无符合条件的比赛）。", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
