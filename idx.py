import json
import asyncio
import requests
import os
import re
from playwright.async_api import Playwright, async_playwright

# 基础配置
BASE_PREFIX = "9000-idx-sherry-"
DOMAIN_PATTERN = f"{BASE_PREFIX}[^.]*.cloudworkstations.dev"

# 常见的真实用户浏览器 User-Agent
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

# 真实的屏幕分辨率
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720}
]

cookies = {
    'WorkstationJwtPartitioned': 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2Nsb3VkLmdvb2dsZS5jb20vd29ya3N0YXRpb25zIiwiYXVkIjoiaWR4LXNoZXJyeS0xNzQ1NzUyMjgzNzQ5LmNsdXN0ZXItaWt4anpqaGxpZmN3dXJvb21ma2pyeDQzN2cuY2xvdWR3b3Jrc3RhdGlvbnMuZGV2IiwiaWF0IjoxNzQ2NzA3MDU1LCJleHAiOjE3NDY3OTMzOTV9.mRGJrxhTNmJ-YTit_SHGSJs9UDIOrBmgRrCqIX0Jio_orzUoVx7MtEzCfR5M2QJonVi98cOJjp0TfDpeNuJ3jnVj9GK0dZjO4bd26eAylCLU-UVt6TStzJLEYohJZHC71naMHDpLTHAajGvT4axxY_EGfyqt5GhjMMOCz_-vTeK_fmIayctGjMVGkogYimmoKfOHKzBkPgT4kSNbUA4NPjAUILVOmjxLcUmksPSdHXAPkO9Q4NEcjNQ2-b3Ax5BlF2W6Ae13pH9NgHPxeaGd2NwmJl5nivRop3E1X7LQ49YLAHGmCzD6D8z4qtoNjC8FibhlRBGvty48sYtexOn13g',
}

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US',
    'Connection': 'keep-alive',
    'Referer': 'https://workstations.cloud.google.com/',
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
}

# 全局消息收集列表
all_messages = []

# 最大页面加载等待时间（秒）
MAX_PAGE_WAIT_TIME = 60
# 元素检测的超时时间（毫秒）
ELEMENT_DETECTION_TIMEOUT = 8000

def log_message(message):
    """记录消息到全局列表并打印"""
    all_messages.append(message)
    print(message)


def send_to_telegram(message):
    bot_token = '5454493483:AAEaEfZ_OWMyFuB6Om_rfHJeZAmN8iBtFoU'
    chat_id = '1918407248'
    if bot_token and chat_id:
        # 检查消息是否为空
        if not message or message.strip() == "":
            print("消息内容为空，不发送Telegram消息")
            return

        # 过滤掉HTML内容和重试信息
        filtered_messages = []
        skip_next_lines = 0

        lines = message.split('\n')
        for i, line in enumerate(lines):
            # 如果设置了跳过行数，则减少计数并跳过当前行
            if skip_next_lines > 0:
                skip_next_lines -= 1
                continue

            # 识别页面响应内容的开始，并跳过它和后面的若干行
            if "页面响应内容片段:" in line:
                skip_next_lines = 5  # 跳过当前行及后续5行
                filtered_messages.append("页面响应内容片段: [已过滤HTML内容]")
                continue

            # 跳过HTML标签
            if ('<!DOCTYPE' in line or
                    '<html' in line.lower() or
                    '</html' in line.lower() or
                    '<head' in line.lower() or
                    '<body' in line.lower() or
                    '<div' in line.lower() or
                    '<span' in line.lower() or
                    '<meta' in line.lower()):
                continue

            # 跳过包含页面HTML片段的行
            if "当前页面HTML片段" in line:
                skip_next_lines = 1  # 跳过下一行，通常是HTML内容
                filtered_messages.append("当前页面HTML片段: [已过滤HTML内容]")
                continue

            # 跳过重试的信息
            if "第2次尝试" in line or "第3次尝试" in line:
                continue

            # 过滤掉特别长的行（可能是HTML内容）
            if len(line) > 300:
                continue

            filtered_messages.append(line)

        # 合并过滤后的消息
        filtered_message = "\n".join(filtered_messages)

        # 添加时间戳
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filtered_message += f"\n\n执行时间: {current_time}"

        # 最后再检查一次是否包含HTML内容
        if "<!DOCTYPE HTML>" in filtered_message or "<html" in filtered_message:
            # 再次过滤，移除所有可能的HTML行
            final_lines = []
            for line in filtered_message.split('\n'):
                if "<" in line and ">" in line and not (
                        "<" in line and ">" in line and len(line) < 50):  # 避免过滤掉正常文本中的<>
                    continue
                final_lines.append(line)
            filtered_message = "\n".join(final_lines)

        # 分段发送，避免消息过长
        max_length = 3800  # Telegram限制约4096字符，留一些余量

        if len(filtered_message) > max_length:
            # 对于超长消息，只发送摘要和关键信息
            summary = "执行结果摘要:\n\n"

            # 提取重要的状态信息
            if "页面状态码200" in filtered_message:
                summary += "✅ 登录成功! 页面状态码200\n"
            if "成功点击元素" in filtered_message:
                summary += "✅ 成功点击了目标元素\n"
            if "IDE主界面四个侧边栏按钮全部加载成功" in filtered_message:
                summary += "✅ IDE界面加载成功\n"
            if "cookie.json" in filtered_message:
                summary += "✅ 已更新cookie.json\n"
            if "已保存最终的cookie状态" in filtered_message:
                summary += "✅ 已更新最终cookie状态\n"

            # 如果没有找到任何成功状态，添加失败信息
            if "✅" not in summary:
                summary += "❌ 执行过程中出现问题，详细日志请查看控制台输出\n"

            # 添加前300个字符和后300个字符的内容摘要，但确保不包含HTML
            summary += "\n部分日志内容:\n"
            # 从前面截取不含HTML的部分
            front_part = ""
            for line in filtered_message[:500].split('\n'):
                if "<" not in line or ">" not in line:
                    front_part += line + "\n"
                if len(front_part) >= 200:
                    break

            # 从后面截取不含HTML的部分
            back_part = ""
            for line in reversed(filtered_message[-500:].split('\n')):
                if "<" not in line or ">" not in line:
                    back_part = line + "\n" + back_part
                if len(back_part) >= 200:
                    break

            summary += front_part[:300] + "\n...\n" + back_part[-300:]

            # 添加时间戳
            summary += f"\n\n执行时间: {current_time}"

            send_single_telegram_message(summary, bot_token, chat_id)
        else:
            # 对于正常长度的消息，直接发送完整内容
            send_single_telegram_message(filtered_message, bot_token, chat_id)


def send_single_telegram_message(message, bot_token, chat_id):
    """发送单个Telegram消息"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message
    }

    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            print(f"Telegram通知发送成功")
        else:
            print(f"Telegram通知发送失败: {response.status_code} - {response.text}")

            # 如果失败，尝试发送更简短的消息
            if len(message) > 1000:
                shorter_message = "执行结果通知: 原消息过长导致发送失败，请查看控制台输出获取完整日志。"
                simple_data = {"chat_id": chat_id, "text": shorter_message}
                try:
                    requests.post(url, data=simple_data)
                    print("已发送简化版通知")
                except:
                    print("简化版通知也发送失败")
    except Exception as e:
        print(f"发送到Telegram失败: {e}")


def extract_domain_from_jwt():
    """从JWT token中提取域名"""
    try:
        jwt_value = extract_workstation_jwt_from_cookies()
        if not jwt_value:
            jwt_value = cookies['WorkstationJwtPartitioned']
        # JWT通常由三部分组成，用.分隔，第二部分包含实际数据
        parts = jwt_value.split('.')
        if len(parts) >= 2:
            import base64
            import json

            # 解码中间部分（可能需要补齐=）
            padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
            decoded = base64.b64decode(padded)
            payload = json.loads(decoded)

            # 从aud字段提取域名
            if 'aud' in payload:
                aud = payload['aud']
                # 使用正则表达式从aud中提取域名
                match = re.search(r'(idx-sherry-[^\.]+\.cluster-[^\.]+\.cloudworkstations\.dev)', aud)
                if match:
                    return f"https://{BASE_PREFIX}{match.group(1).split('idx-sherry-')[1]}"

        # 如果无法提取，使用默认域名
        return f"https://{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"
    except Exception as e:
        log_message(f"提取域名时出错: {e}")
        return f"https://{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"


async def run(playwright: Playwright) -> bool:
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        # 随机选择User-Agent和视口大小，使每次请求看起来更加真实
        random_user_agent = USER_AGENTS[attempt % len(USER_AGENTS)]
        random_viewport = VIEWPORT_SIZES[attempt % len(VIEWPORT_SIZES)]

        # 增强无头模式的伪装能力
        browser_args = [
            # 基础反检测配置
            '--disable-blink-features=AutomationControlled',
            # 禁用默认的headless检测向量
            '--no-sandbox',
            # 其他必要参数
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-size=1366,768',
            '--start-maximized',
            # 在Windows上特别有用的参数
            '--disable-gpu',
            '--disable-dev-shm-usage',
        ]

        # 使用有头模式以避免headless特征检测
        browser = await playwright.chromium.launch(
            headless=True,
            slow_mo=300,  # 减少延迟时间
            args=browser_args
        )

        try:
            # 尝试使用storage_state加载之前保存的状态
            storage_state_options = {}
            if os.path.exists("cookie.json"):
                # 检查cookie.json文件是否有效
                try:
                    with open("cookie.json", "r") as f:
                        cookie_data = json.load(f)
                    # 检查是否包含必要的数据结构
                    if "cookies" not in cookie_data or not isinstance(cookie_data["cookies"], list):
                        log_message("警告：cookie.json文件结构有问题，将创建新的cookie")
                        # 创建一个最小的cookie文件结构
                        with open("cookie.json", "w") as f:
                            json.dump({"cookies": [], "origins": []}, f)
                    else:
                        log_message(f"第{attempt}次尝试：从cookie.json加载存储状态，文件有效")
                        storage_state_options["storage_state"] = "cookie.json"
                except Exception as e:
                    log_message(f"警告：cookie.json文件读取失败 - {e}，将创建新的cookie")
                    # 创建一个最小的cookie文件结构
                    with open("cookie.json", "w") as f:
                        json.dump({"cookies": [], "origins": []}, f)
            else:
                log_message("cookie.json文件不存在，将创建一个空的cookie文件")
                # 创建一个最小的cookie文件结构
                with open("cookie.json", "w") as f:
                    json.dump({"cookies": [], "origins": []}, f)

            # 创建浏览器上下文
            context = await browser.new_context(
                user_agent=random_user_agent,
                # 更真实的设备参数
                device_scale_factor=1.0,
                has_touch=False,
                is_mobile=False,
                locale="en-US",
                timezone_id="America/New_York",
                java_script_enabled=True,
                bypass_csp=True,
                # 模拟真实浏览器的颜色方案和媒体设置
                color_scheme="light",
                reduced_motion="no-preference",
                forced_colors="none",
                **storage_state_options  # 添加storage_state参数（如果文件存在）
            )
            
            page = await context.new_page()
            
            # 使页面可见并放大到前台
            await page.bring_to_front()
            
            # 简化页面反检测代码
            await page.evaluate("""() => {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                delete navigator.__proto__.webdriver;
            }""")
            
            log_message("正在访问idx.google.com...")
            
            try:
                # 设置合理的超时时间
                page.set_default_timeout(MAX_PAGE_WAIT_TIME * 1000)  # 转换为毫秒
                
                # 导航到页面
                await page.goto("https://idx.google.com/")
                log_message("已发送页面请求，等待页面加载...")
                await asyncio.sleep(20)  # 等待20秒，确保登录弹窗加载完毕
                # 检查并自动勾选Firebase Studio条款弹窗，增加重试机制
                max_checkbox_retries = 3
                for checkbox_attempt in range(1, max_checkbox_retries + 1):
                    try:
                        # 最佳方法：使用ID直接选择复选框并使用check()方法
                        await page.locator("#utos-checkbox").check()
                        log_message(f"第{checkbox_attempt}次尝试：已勾选条款复选框")

                        # 等待2秒，确保按钮状态刷新
                        await asyncio.sleep(2)

                        # 使用角色和名称定位Confirm按钮并点击
                        await page.get_by_role("button", name="Confirm").click()
                        log_message(f"第{checkbox_attempt}次尝试：已点击Confirm按钮")
                        break  # 成功则跳出重试循环
                    except Exception as e:
                        log_message(f"第{checkbox_attempt}次尝试：自动勾选条款并点击Confirm失败: {e}")
                        if checkbox_attempt < max_checkbox_retries:
                            # 重新加载cookie.json
                            try:
                                if os.path.exists("cookie.json"):
                                    with open("cookie.json", "r") as f:
                                        cookie_data = json.load(f)
                                    log_message(f"第{checkbox_attempt}次重试：已重新加载cookie.json")
                            except Exception as ce:
                                log_message(f"第{checkbox_attempt}次重试：重新加载cookie.json失败: {ce}")
                            await asyncio.sleep(2)
                        else:
                            log_message("已达到最大重试次数，跳过条款勾选流程")
                
                # 使用Promise.race同时等待多个事件，哪个先完成就继续
                try:
                    log_message("等待页面加载完成...")
                    # 使用更短的超时时间等待页面加载状态
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    log_message("DOM内容已加载")
                    
                    # 立即检查页面上是否已有workspace图标元素
                    workspace_selectors = [
                        'div[class="workspace-icon"]',
                        'img[src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
                        '.workspace-icon',
                        'img[role="presentation"][class="custom-icon"]'
                    ]
                    
                    # 先快速检查元素是否存在，不等待太久
                    for selector in workspace_selectors:
                        try:
                            element = await page.wait_for_selector(selector, timeout=2000)
                            if element:
                                log_message(f"页面已预加载完成，找到workspace图标元素! 使用选择器: {selector}")
                                break
                        except Exception:
                            continue
                    
                    # 继续等待其它加载状态，但不阻塞流程
                    try:
                        await page.wait_for_load_state("networkidle", timeout=20000)
                        log_message("网络活动已稳定")
                    except Exception as e:
                        log_message(f"等待网络稳定超时，但这不会阻塞流程: {e}")
                        
                except Exception as e:
                    log_message(f"等待初始DOM加载超时: {e}")
                    # 如果等待DOM超时，尝试等待常见元素出现
                    pass
                
                # 短暂暂停，等待页面渲染
                await asyncio.sleep(5)
                
                # 检查工作区图标元素是否出现
                log_message("检查workspace图标元素是否出现...")
                login_success = False
                workspace_selectors = [
                    'div[class="workspace-icon"]',
                    'img[src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
                    '.workspace-icon',
                    'img[role="presentation"][class="custom-icon"]'
                ]
                
                for selector in workspace_selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=ELEMENT_DETECTION_TIMEOUT)
                        if element:
                            log_message(f"找到workspace图标元素! 使用选择器: {selector}")
                            login_success = True
                            break
                    except Exception:
                        continue
                
                if not login_success:
                    log_message(f"第{attempt}次尝试：登录验证失败，未找到workspace图标元素")
                    
                    # 尝试截图记录当前页面状态
                    try:
                        screenshot_path = f"page_state_attempt_{attempt}.png"
                        await page.screenshot(path=screenshot_path)
                        log_message(f"已保存当前页面截图到 {screenshot_path}")
                    except Exception as e:
                        log_message(f"截图失败: {e}")
                    
                    await context.close()
                    await browser.close()
                    
                    if attempt == max_retries:
                        log_message("已达到最大重试次数，流程终止")
                        raise Exception("验证登录失败，未找到workspace图标元素，已重试3次")
                    else:
                        continue
                else:
                    log_message("登录验证成功：找到workspace图标元素，确认登录成功!")
                
                # 保存cookie到cookie.json
                await context.storage_state(path="cookie.json")
                log_message("已更新idx.google.com的存储状态到cookie.json")
                
                # 使用requests进行协议检查
                check_result = check_page_status_with_requests()
                if check_result:
                    log_message("【检查结果】工作站可直接通过协议访问（状态码200），直接退出")
                    # 直接退出，不进行后续操作
                    await context.close()
                    await browser.close()
                    return True  # 返回True表示检查成功
                else:
                    log_message("【检查结果】工作站不可通过协议直接访问（状态码非200），继续执行后续步骤")
                
                # 点击workspace图标
                log_message("使用多种方法尝试点击workspace图标元素...")
                exact_selectors = [
                    'div[class="workspace-icon"]',
                    'img[src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
                    '.workspace-icon',
                    'img[role="presentation"][class="custom-icon"]',
                    'div[_ngcontent-ng-c2464377164][class="workspace-icon"]',
                    'div[_ngcontent-ng-c2464377164].workspace-icon',
                    'img[_ngcontent-ng-c2464377164][class="custom-icon"][src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
                    'div[_ngcontent-ng-c][class="workspace-icon"]',
                    'img[_ngcontent-ng-c][class="custom-icon"]',
                    'div.workspace-icon img.custom-icon',
                    '.workspace-icon img'
                ]
                
                success = False
                for selector in exact_selectors:
                    if success:
                        break
                    try:
                        log_message(f"尝试选择器: {selector}")
                        element = await page.wait_for_selector(selector, timeout=3000)
                        if element:
                            log_message(f"找到元素! 使用选择器: {selector}")
                            try:
                                # 尝试多种点击方法
                                try:
                                    await element.click(force=True)  # 使用force参数强制点击
                                    log_message(f"成功点击元素! 使用选择器: {selector}")
                                    success = True
                                    break
                                except Exception as e:
                                    log_message(f"直接点击失败: {e}，尝试JavaScript点击")
                                    try:
                                        await page.evaluate("(element) => element.click()", element)
                                        log_message(f"使用JavaScript成功点击元素! 使用选择器: {selector}")
                                        success = True
                                        break
                                    except Exception as js_e:
                                        log_message(f"JavaScript点击失败: {js_e}，尝试点击父元素")
                                        try:
                                            await page.evaluate("""(element) => {
                                                const clickableEl = element.closest('a') || element.closest('button') || element.parentElement;
                                                if(clickableEl) {
                                                    clickableEl.click();
                                                    return true;
                                                }
                                                return false;
                                            }""", element)
                                            log_message(f"尝试点击父元素或最近的可点击元素! 使用选择器: {selector}")
                                            success = True
                                            break
                                        except Exception as p_e:
                                            log_message(f"尝试点击父元素或最近的可点击元素失败: {p_e}")
                            except Exception as e:
                                log_message(f"点击操作失败: {e}")
                    except Exception as e:
                        log_message(f"选择器 {selector} 未找到元素: {e}")
                
                if success:
                    log_message(f"第{attempt}次尝试：成功点击元素，流程继续")
                    log_message("等待页面响应...")
                    await asyncio.sleep(10)
                    
                    # 检测是否成功进入IDE页面
                    log_message("检测是否成功进入IDE页面...")
                    current_url = page.url
                    log_message(f"当前URL: {current_url}")
                    
                    if "sherry" in current_url or "workspace" in current_url or "cloudworkstations" in current_url:
                        log_message("URL已变化，确认进入新页面，等待IDE主界面元素...")

                        # 使用更合理的等待时间
                        log_message("等待加载空间，这可能需要180秒...")
                        await asyncio.sleep(180)  # 从150秒减少到60秒
                        log_message("等待结束，开始检测侧边栏元素...")

                        max_refresh_retries = 3
                        for refresh_attempt in range(1, max_refresh_retries + 1):
                            try:
                                # 打印页面部分HTML，便于调试
                                html = await page.content()
                                log_message("当前页面HTML片段：" + html[:2000])
                                
                                # 检查是否有iframe
                                frames = page.frames
                                target = page
                                for frame in frames:
                                    try:
                                        frame_html = await frame.content()
                                        if 'codicon-explorer-view-icon' in frame_html:
                                            target = frame
                                            log_message("已自动切换到包含目标元素的iframe")
                                            break
                                    except Exception:
                                        continue
                                
                                # 定义侧边栏按钮选择器
                                btn_selectors = [
                                    '[class*="codicon-explorer-view-icon"], [aria-label*="Explorer"]',
                                    '[class*="codicon-search-view-icon"], [aria-label*="Search"]',
                                    '[class*="codicon-source-control-view-icon"], [aria-label*="Source Control"]',
                                    '[class*="codicon-run-view-icon"], [aria-label*="Run and Debug"]',
                                ]
                                
                                # 依次等待四个按钮，使用更短的超时时间
                                found_buttons = 0
                                for sel in btn_selectors:
                                    try:
                                        await target.wait_for_selector(sel, timeout=20000)
                                        found_buttons += 1
                                        log_message(f"找到按钮 {found_buttons}/4: {sel}")
                                    except Exception as e:
                                        log_message(f"未找到按钮: {sel}, 错误: {e}")
                                        # 即使某个按钮未找到，也继续检查其他按钮
                                        continue
                                
                                if found_buttons > 0:
                                    log_message(f"IDE主界面找到 {found_buttons}/4 个侧边栏按钮（第{refresh_attempt}次刷新尝试）")
                                    # 只有找到至少3个按钮才认为成功，否则继续尝试
                                    if found_buttons >= 3:
                                        log_message(f"找到足够的侧边栏按钮 ({found_buttons}/4)，认为界面加载成功")
                                        
                                        # 停留较短时间
                                        log_message("停留15秒以确保页面完全加载...")
                                        await asyncio.sleep(15)
                                        
                                        # 更新最终cookie状态
                                        await context.storage_state(path="last_cookie.json")
                                        log_message("已更新最终的存储状态到last_cookie.json")
                                        
                                        # 提取并更新代码中的值
                                        update_domain_and_jwt_in_code()
                                        break  # 成功后跳出刷新循环
                                    else:
                                        log_message(f"找到的按钮数量不足 ({found_buttons}/4)，需要至少3个按钮才认为成功")
                                        if refresh_attempt < max_refresh_retries:
                                            log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                                            await page.reload()
                                            await asyncio.sleep(5)
                                        else:
                                            log_message("已达到最大刷新重试次数，未能找到足够的侧边栏按钮")
                                            raise Exception("未能找到足够的侧边栏按钮，流程失败")
                                else:
                                    log_message(f"未找到任何侧边栏按钮，尝试刷新...")
                                    if refresh_attempt < max_refresh_retries:
                                        log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                                        await page.reload()
                                        await asyncio.sleep(5)
                                    else:
                                        log_message("已达到最大刷新重试次数，未能找到任何侧边栏按钮")
                                        raise Exception("未能找到任何侧边栏按钮，流程失败")
                            except Exception as e:
                                log_message(f"第{refresh_attempt}次刷新尝试：等待IDE主界面元素时出错: {e}")
                                if refresh_attempt < max_refresh_retries:
                                    log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                                    await page.reload()
                                    await asyncio.sleep(5)
                                else:
                                    log_message("已达到最大刷新重试次数，无法完成检测")
                                    raise Exception("刷新后仍然无法完成侧边栏按钮检测，流程失败")
                    else:
                        log_message("URL未变化，未检测到IDE页面")
                    
                    await context.close()
                    await browser.close()
                    # 如果已经执行了整个过程，说明成功了
                    return True  # 返回True表示成功完成流程
                else:
                    log_message(f"第{attempt}次尝试：未能点击到元素，准备重试...")
                    
                    # 尝试截图记录当前页面状态
                    try:
                        screenshot_path = f"click_failed_attempt_{attempt}.png"
                        await page.screenshot(path=screenshot_path)
                        log_message(f"已保存点击失败截图到 {screenshot_path}")
                    except Exception as e:
                        log_message(f"截图失败: {e}")
                    
                    await context.close()
                    await browser.close()
                    
                    if attempt == max_retries:
                        log_message("已达到最大重试次数，流程终止")
                        raise Exception("加载cookie和点击元素失败，已重试3次")
                    else:
                        continue
            except Exception as e:
                log_message(f"第{attempt}次尝试：页面加载或处理过程中出错: {e}")
                
                # 尝试截图记录当前页面状态
                try:
                    screenshot_path = f"error_attempt_{attempt}.png"
                    await page.screenshot(path=screenshot_path)
                    log_message(f"已保存错误截图到 {screenshot_path}")
                except Exception as se:
                    log_message(f"截图失败: {se}")
                
                await context.close()
                await browser.close()
                
                if attempt == max_retries:
                    raise
                else:
                    continue
        except Exception as e:
            log_message(f"上下文创建失败: {e}")
            try:
                await browser.close()
            except:
                pass
            
            if attempt == max_retries:
                raise
            else:
                continue
    
    return False  # 所有尝试都失败


def check_page_status_with_requests():
    """使用requests协议方式直接检查页面状态"""
    try:
        # 首先尝试从全局变量中获取JWT
        jwt = cookies.get('WorkstationJwtPartitioned')

        # 尝试提取域名
        domain = f"{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"

        # 如果有last_cookie.json，优先从中提取JWT和域名
        if os.path.exists("last_cookie.json"):
            try:
                with open("last_cookie.json", "r") as file:
                    storage_data = json.load(file)
                    # 从storage_state格式中提取cookies
                    cookies_data = storage_data.get('cookies', [])

                # 尝试提取JWT
                for cookie in cookies_data:
                    if cookie.get('name') == 'WorkstationJwtPartitioned':
                        jwt = cookie.get('value')
                        log_message("从last_cookie.json中提取到JWT")
                        break

                # 尝试提取域名
                domain_pattern = f"{BASE_PREFIX}[^.]+\\.cluster-[^.]+\\.cloudworkstations\\.dev"
                for cookie in cookies_data:
                    if 'domain' in cookie:
                        match = re.search(domain_pattern, cookie['domain'])
                        if match:
                            domain = match.group(0)
                            log_message(f"从last_cookie.json的cookie domain提取到域名: {domain}")
                            break
            except Exception as e:
                log_message(f"读取last_cookie.json出错: {e}")

        # 如果仍然无法获取域名，从JWT中尝试提取
        if jwt and domain == f"{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev":
            try:
                parts = jwt.split('.')
                if len(parts) >= 2:
                    import base64

                    # 解码JWT的payload部分
                    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    decoded = base64.b64decode(padded)
                    payload = json.loads(decoded)

                    # 从aud字段提取域名
                    if 'aud' in payload:
                        aud = payload['aud']
                        domain_match = re.search(domain_pattern, aud)
                        if domain_match:
                            domain = domain_match.group(1)
                            log_message(f"从JWT的aud字段提取到域名: {domain}")
            except Exception as e:
                log_message(f"从JWT提取域名时出错: {e}")

        # 构建请求
        request_cookies = {
            'WorkstationJwtPartitioned': jwt,
        }

        url = f'https://{domain}/'
        log_message(f"正在使用requests协议方式验证页面状态，URL: {url}")
        log_message(f"使用的JWT前20字符: {jwt[:20]}...")

        # 发送请求获取页面状态
        response = requests.get(
            url,
            cookies=request_cookies,
            headers=headers,
            timeout=15
        )

        log_message(f"页面状态码: {response.status_code}")

        # 输出响应内容的前200个字符，便于调试
        if response.status_code == 200:
            log_message("页面状态码200，工作站可以直接通过协议访问")
            log_message(f"页面响应内容片段: {response.text[:200]}")
            return True
        else:
            log_message(f"页面状态码为{response.status_code}，无法直接通过协议访问")
            log_message(f"错误响应内容片段: {response.text[:200] if response.text else '无响应内容'}")
            return False
    except Exception as e:
        log_message(f"使用requests协议检查页面状态时出错: {e}")
        return False


def extract_workstation_jwt_from_cookies():
    try:
        with open("last_cookie.json", "r") as file:  # 从last_cookie.json提取
            storage_data = json.load(file)
            # 从storage_state格式中提取cookies
            cookies_data = storage_data.get('cookies', [])
        for cookie in cookies_data:
            if cookie.get('name') == 'WorkstationJwtPartitioned':
                return cookie.get('value')
        return None
    except Exception as e:
        log_message(f"从last_cookie.json提取WorkstationJwtPartitioned失败: {e}")
        return None


def update_cookie_in_source_code(new_jwt_value):
    if not new_jwt_value:
        log_message("没有有效的JWT值，无法更新源代码")
        return False
    try:
        with open(__file__, "r", encoding="utf-8") as file:
            content = file.read()
        pattern = r"'WorkstationJwtPartitioned': '([^']*)',"
        updated_content = re.sub(pattern,
                                 f"'WorkstationJwtPartitioned': 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2Nsb3VkLmdvb2dsZS5jb20vd29ya3N0YXRpb25zIiwiYXVkIjoiaWR4LXNoZXJyeS0xNzQ1NzUyMjgzNzQ5LmNsdXN0ZXItaWt4anpqaGxpZmN3dXJvb21ma2pyeDQzN2cuY2xvdWR3b3Jrc3RhdGlvbnMuZGV2IiwiaWF0IjoxNzQ2NzA3MDU1LCJleHAiOjE3NDY3OTMzOTV9.mRGJrxhTNmJ-YTit_SHGSJs9UDIOrBmgRrCqIX0Jio_orzUoVx7MtEzCfR5M2QJonVi98cOJjp0TfDpeNuJ3jnVj9GK0dZjO4bd26eAylCLU-UVt6TStzJLEYohJZHC71naMHDpLTHAajGvT4axxY_EGfyqt5GhjMMOCz_-vTeK_fmIayctGjMVGkogYimmoKfOHKzBkPgT4kSNbUA4NPjAUILVOmjxLcUmksPSdHXAPkO9Q4NEcjNQ2-b3Ax5BlF2W6Ae13pH9NgHPxeaGd2NwmJl5nivRop3E1X7LQ49YLAHGmCzD6D8z4qtoNjC8FibhlRBGvty48sYtexOn13g',",
                                 content)
        with open(__file__, "w", encoding="utf-8") as file:
            file.write(updated_content)
        log_message("成功更新源代码中的WorkstationJwtPartitioned值")
        return True
    except Exception as e:
        log_message(f"更新源代码中的WorkstationJwtPartitioned值失败: {e}")
        return False


# 提取9000-idx-sherry-开头的域名和WorkstationJwtPartitioned并更新到代码
def update_domain_and_jwt_in_code():
    try:
        # 确认last_cookie.json是否存在
        if not os.path.exists("last_cookie.json"):
            log_message("last_cookie.json不存在，无法更新代码中的域名和JWT")
            return

        with open("last_cookie.json", "r") as f:  # 从last_cookie.json读取
            storage_data = json.load(f)
            # 从storage_state格式中提取cookies
            cookies_data = storage_data.get('cookies', [])

        # 提取JWT
        jwt = None
        for cookie in cookies_data:
            if cookie.get('name') == 'WorkstationJwtPartitioned':
                jwt = cookie.get('value')
                break

        if not jwt:
            log_message("未在last_cookie.json中找到WorkstationJwtPartitioned，无法更新代码")
            return

        # 提取域名
        domain = None
        domain_pattern = r"(9000-idx-sherry-[^\.]+\.cluster-[^\.]+\.cloudworkstations\.dev)"

        # 先从cookie的domain字段尝试提取
        for cookie in cookies_data:
            if 'domain' in cookie:
                match = re.search(domain_pattern, cookie['domain'])
                if match:
                    domain = match.group(1)
                    log_message(f"从cookie domain字段提取到域名: {domain}")
                    break

        # 如果从cookie未找到域名，尝试从JWT解析
        if not domain:
            try:
                parts = jwt.split('.')
                if len(parts) >= 2:
                    import base64
                    # 解码JWT的payload部分
                    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    decoded = base64.b64decode(padded)
                    payload = json.loads(decoded)

                    # 从aud字段提取域名
                    if 'aud' in payload:
                        aud = payload['aud']
                        domain_match = re.search(domain_pattern, aud)
                        if domain_match:
                            domain = domain_match.group(1)
                            log_message(f"从JWT的aud字段提取到域名: {domain}")
            except Exception as e:
                log_message(f"从JWT解析域名时出错: {e}")

        # 更新代码中的JWT和域名
        with open(__file__, "r", encoding="utf-8") as file:
            content = file.read()

        # 更新JWT
        pattern_jwt = r"'WorkstationJwtPartitioned': '([^']*)',"
        updated_content = re.sub(pattern_jwt,
                                 f"'WorkstationJwtPartitioned': 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2Nsb3VkLmdvb2dsZS5jb20vd29ya3N0YXRpb25zIiwiYXVkIjoiaWR4LXNoZXJyeS0xNzQ1NzUyMjgzNzQ5LmNsdXN0ZXItaWt4anpqaGxpZmN3dXJvb21ma2pyeDQzN2cuY2xvdWR3b3Jrc3RhdGlvbnMuZGV2IiwiaWF0IjoxNzQ2NzA3MDU1LCJleHAiOjE3NDY3OTMzOTV9.mRGJrxhTNmJ-YTit_SHGSJs9UDIOrBmgRrCqIX0Jio_orzUoVx7MtEzCfR5M2QJonVi98cOJjp0TfDpeNuJ3jnVj9GK0dZjO4bd26eAylCLU-UVt6TStzJLEYohJZHC71naMHDpLTHAajGvT4axxY_EGfyqt5GhjMMOCz_-vTeK_fmIayctGjMVGkogYimmoKfOHKzBkPgT4kSNbUA4NPjAUILVOmjxLcUmksPSdHXAPkO9Q4NEcjNQ2-b3Ax5BlF2W6Ae13pH9NgHPxeaGd2NwmJl5nivRop3E1X7LQ49YLAHGmCzD6D8z4qtoNjC8FibhlRBGvty48sYtexOn13g',",
                                 content)

        # 如果找到了域名，也可以更新默认域名（如果需要）
        if domain:
            pattern_domain = r'domain = f"{BASE_PREFIX}1745752283749\.cluster-ikxjzjhlifcwuroomfkjrx437g\.cloudworkstations\.dev"'
            domain_id = domain.split(f"{BASE_PREFIX}")[1].split(".cluster")[0]
            cluster_id = domain.split("cluster-")[1].split(".cloud")[0]
            updated_content = re.sub(pattern_domain,
                                     f'domain = f"{{BASE_PREFIX}}{domain_id}.cluster-{cluster_id}.cloudworkstations.dev"',
                                     updated_content)
            log_message(f"已提取域名ID: {domain_id}, 集群ID: {cluster_id}")

        with open(__file__, "w", encoding="utf-8") as file:
            file.write(updated_content)

        log_message(f"已更新源代码中的WorkstationJwtPartitioned值和域名信息")
    except Exception as e:
        log_message(f"更新源代码中的值失败: {e}")


async def update_cookie_with_playwright():
    """使用playwright更新cookie.json和进行自动化操作"""
    global all_messages
    all_messages = []
    log_message("启动playwright更新cookie和执行自动化操作...")
    async with async_playwright() as playwright:
        success = await run(playwright)
    log_message(f"playwright执行完成，结果: {'成功' if success else '失败'}")
    if not success:
        log_message("自动化登录流程失败，请检查错误日志")


async def main():
    try:
        log_message("开始执行主流程...")

        # 先用requests协议方式直接检查页面状态
        check_result = check_page_status_with_requests()
        if check_result:
            log_message("【检查结果】工作站可直接通过协议访问（状态码200），流程直接退出")
            if all_messages:
                full_message = "\n".join(all_messages)
                send_to_telegram(full_message)
            return
        else:
            log_message("【检查结果】工作站不可通过协议直接访问（状态码非200），继续执行playwright自动化流程")

        # 使用playwright加载cookie.json，登录idx.google.com，然后通过requests检查工作站状态
        await update_cookie_with_playwright()

        # 整体发送收集到的所有消息
        if all_messages:
            full_message = "\n".join(all_messages)
            send_to_telegram(full_message)
    except Exception as e:
        log_message(f"主流程执行出错: {e}")
        # 确保错误信息也被发送
        if all_messages:
            full_message = "\n".join(all_messages)
            send_to_telegram(full_message)


if __name__ == "__main__":
    all_messages = []
    asyncio.run(main())
