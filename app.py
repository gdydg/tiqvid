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
DEBUG_FILE_PATH = 'debug_page.html' # 新增：用于保存调试网页

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
    
    target_ids = set()
    debug_saved = False # 标记是否已经保存过调试文件，只存一次就够了
    
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
        
        if -3 <= time_diff <= 3:
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
                            
                            # 注意：这行正是原来提取失败的地方！
                            id_match = re.search(r'paps\.html\?id=([A-Za-z0-9+/=]+)', play_res.text)
                            
                            if id_match:
                                target_ids.add(id_match.group(1))
                            else:
                                # 如果内容大于 100 字符（排除那个只有一个点 '.' 的页面）并且还没保存过
                                if len(play_res.text) > 100 and not debug_saved:
                                    with open(DEBUG_FILE_PATH, 'w', encoding='utf-8') as df:
                                        df.write(play_res.text)
                                    debug_saved = True
                                    print(f"⚠️ 发现格式不匹配的页面！已将网页源码保存至 /{DEBUG_FILE_PATH} 供排查。")

                except Exception as e:
                    pass

    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        for item in target_ids:
            f.write(item + '\n')
    
    print(f"🎉 抓取任务完成！共提取 {len(target_ids)} 个不重复的 ID。")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(func=scrape_task, trigger="interval", minutes=30, id='scrape_job', replace_existing=True)
scheduler.start()

scrape_task()

@app.route('/')
def get_ids():
    if os.path.exists(FILE_PATH) and os.path.getsize(FILE_PATH) > 0:
        return send_file(FILE_PATH, mimetype='text/plain')
    return "✅ 抓取运行完成。但未提取到ID。请访问 /debug 查看失败页面的源码", 200

# 新增一个接口，让你直接在浏览器里查看那个包含真实 ID 结构的 HTML
@app.route('/debug')
def view_debug():
    if os.path.exists(DEBUG_FILE_PATH):
        return send_file(DEBUG_FILE_PATH, mimetype='text/html')
    return "暂时没有抓取到可以调试的页面", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
