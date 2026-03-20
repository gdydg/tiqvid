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

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 开始执行抓取任务...")
    
    js_url = 'https://im-imgs-bucket.oss-accelerate.aliyuncs.com/index.js?t_5'
    try:
        response = requests.get(js_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        response.raise_for_status()
    except Exception as e:
        print(f"❌ 请求主 JS 失败: {e}")
        return

    # 提取 HTML 并解析
    html_snippets = re.findall(r"document\.write\('(.*?)'\);", response.text)
    html_content = "".join(html_snippets)
    soup = BeautifulSoup(html_content, 'html.parser')

    match_lists = soup.find_all('ul', class_='item play')
    print(f"📊 成功解析 JS 文件，共找到 {len(match_lists)} 场比赛信息。")

    target_ids = set()
    
    for match in match_lists:
        time_li = match.find('li', class_='lab_time')
        if not time_li:
            continue
        
        time_str = time_li.text.strip()
        try:
            # 格式化时间
            match_time_naive = datetime.strptime(f"{current_year}-{time_str}", "%Y-%m-%d %H:%M")
            match_time = tz.localize(match_time_naive)
            
            # 跨年处理
            if match_time > now + timedelta(days=300):
                match_time = tz.localize(match_time_naive.replace(year=current_year - 1))
            elif match_time < now - timedelta(days=300):
                match_time = tz.localize(match_time_naive.replace(year=current_year + 1))
        except ValueError:
            continue

        # 计算时间差（小时）
        time_diff = (match_time - now).total_seconds() / 3600
        
        # 筛选前后 3 小时内的比赛
        if -3 <= time_diff <= 3:
            print(f"🕒 发现时间符合的比赛: {time_str} (相差 {time_diff:.1f} 小时)")
            links = match.find_all('a', href=re.compile(r'play\.sportsteam368\.com'))
            
            if not links:
                print("   ⚠️ 警告: 该比赛下未找到 play.sportsteam368.com 的链接。")
                continue

            for link in links:
                match_url = link.get('href')
                print(f"   🔗 正在访问赛事详情: {match_url}")
                
                try:
                    match_res = requests.get(match_url, headers=headers, timeout=10)
                    match_res.encoding = 'utf-8'
                    match_soup = BeautifulSoup(match_res.text, 'html.parser')
                    
                    # 【核心修复】：遍历所有 a 标签，只要内部文本包含“高清直播”就提取，无视内部的 html 结构
                    hd_links = [a for a in match_soup.find_all('a') if a.get_text() and '高清直播' in a.get_text()]
                    
                    if not hd_links:
                        print("   ❌ 未在该详情页找到带有 '高清直播' 字样的选项。")
                        continue

                    for hd in hd_links:
                        data_play = hd.get('data-play')
                        if data_play:
                            play_url = f"http://play.sportsteam368.com{data_play}"
                            print(f"     ➡️ 找到高清直播播放页: {play_url}")
                            
                            play_res = requests.get(play_url, headers=headers, timeout=10)
                            id_match = re.search(r'paps\.html\?id=([A-Za-z0-9+/=]+)', play_res.text)
                            
                            if id_match:
                                extracted_id = id_match.group(1)
                                target_ids.add(extracted_id)
                                print(f"     ✅ 成功提取 ID: {extracted_id[:10]}...")
                            else:
                                print(f"     ❌ 未在播放页源码中正则匹配到 paps.html?id=xxx")
                except Exception as e:
                    print(f"   ❌ 请求详情页失败: {e}")

    # 写入文件
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        for item in target_ids:
            f.write(item + '\n')
    
    print(f"\n🎉 抓取任务完成！共提取 {len(target_ids)} 个不重复的 ID。")

# 定时任务：每 30 分钟一次
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
scheduler.add_job(func=scrape_task, trigger="interval", minutes=30, id='scrape_job', replace_existing=True)
scheduler.start()

# 启动时先执行一次
scrape_task()

@app.route('/')
def get_ids():
    """优化后的 Web 路由"""
    if os.path.exists(FILE_PATH):
        if os.path.getsize(FILE_PATH) > 0:
            return send_file(FILE_PATH, mimetype='text/plain')
        else:
            return "✅ 抓取脚本运行正常，但目前文件中没有任何 ID（可能当前前后3小时无符合条件的比赛）。请去后台查看 Logs 获取详细抓取过程！", 200
    return "⏳ 系统初始化中或抓取任务正在进行，请稍后刷新...", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
