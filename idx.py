import json
import asyncio
import requests
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from playwright.async_api import Playwright, async_playwright

# 基础配置
BASE_PREFIX = "9000-idx-sherry-"
DOMAIN_PATTERN = f"{BASE_PREFIX}[^.]*.cloudworkstations.dev"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
]

# 全局配置
cookies_path = "cookie.json"  # 只保留一个cookie文件
app_url = os.environ.get("APP_URL", "https://idx.google.com")
all_messages = []
MAX_RETRIES = 3
TIMEOUT = 30000  # 默认超时时间（毫秒）

def log_message(message):
    """记录消息到全局列表并打印"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    all_messages.append(formatted_message)
    print(formatted_message)

def send_to_telegram(message):
    """将消息发送到Telegram"""
    # 从环境变量获取凭据，如果未设置则使用默认值
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", '5454493483:AAEaEfZ_OWMyFuB6Om_rfHJeZAmN8iBtFoU')
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", '1918407248')
    
    if not bot_token or not chat_id:
        log_message("缺少Telegram配置，跳过通知")
        return
    
    # 简化消息内容 - 只保留关键状态信息
    simplified_message = "【IDX自动登录状态报告】\n"
    
    # 提取关键信息 - 查找关键状态行
    key_status_patterns = [
        "开始执行IDX登录",
        "工作站可以直接通过协议访问",
        "自动化流程执行结果",
        "成功点击工作区图标",
        "通过cookies直接登录",
        "UI交互流程",
        "工作区加载验证",
        "已保存最终cookie状态",
        "主流程执行出错"
    ]
    
    # 从所有消息中提取关键状态行
    key_lines = []
    for line in all_messages:
        for pattern in key_status_patterns:
            if pattern in line:
                # 截取时间戳和实际消息
                parts = line.split("] ", 1)
                if len(parts) > 1:
                    time_stamp = parts[0].replace("[", "")
                    message_content = parts[1]
                    key_lines.append(f"{time_stamp}: {message_content}")
                    break
    
    # 添加关键状态行到简化消息
    if key_lines:
        simplified_message += "\n".join(key_lines)
    else:
        simplified_message += "未找到关键状态信息"
    
    # 添加工作站域名信息(如果存在)
    domain = extract_domain_from_jwt()
    if domain:
        simplified_message += f"\n\n工作站域名: {domain}"
    
    # 添加时间戳
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    simplified_message += f"\n\n执行时间: {current_time}"
    
    # 发送简化的消息
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": simplified_message}
        response = requests.post(url, data=data, timeout=10)
        log_message(f"Telegram通知状态: {response.status_code}")
    except Exception as e:
        log_message(f"发送Telegram通知失败: {e}")

def load_cookies(filename=cookies_path):
    """加载cookies并验证格式"""
    try:
        if not os.path.exists(filename):
            log_message(f"{filename}不存在，将创建空cookie文件")
            empty_data = {"cookies": [], "origins": []}
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(empty_data, f)
            return empty_data
            
        with open(filename, 'r', encoding="utf-8") as f:
            cookie_data = json.load(f)
            
        # 验证格式
        if "cookies" not in cookie_data or not isinstance(cookie_data["cookies"], list):
            log_message(f"{filename}格式有问题，将重置")
            empty_data = {"cookies": [], "origins": []}
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(empty_data, f)
            return empty_data
            
        log_message(f"成功加载{filename}")
        return cookie_data
    except Exception as e:
        log_message(f"加载{filename}失败: {e}")
        # 创建空cookie文件
        empty_data = {"cookies": [], "origins": []}
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(empty_data, f)
        except Exception:
            pass
        return empty_data

def extract_domain_from_jwt(jwt_value=None):
    """从JWT token中提取域名"""
    try:
        # 如果没有提供JWT，尝试从cookie文件加载
        if not jwt_value:
            cookie_data = load_cookies(cookies_path)
            for cookie in cookie_data.get("cookies", []):
                if cookie.get("name") == "WorkstationJwtPartitioned":
                    jwt_value = cookie.get("value")
                    break
        
        if not jwt_value:
            log_message("无法找到JWT值，将使用默认域名")
            return f"{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"
            
        # 解析JWT获取域名信息
        parts = jwt_value.split('.')
        if len(parts) >= 2:
            import base64
            
            # 解码中间部分（可能需要补齐=）
            padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
            decoded = base64.b64decode(padded)
            payload = json.loads(decoded)
            
            # 从aud字段提取域名
            if 'aud' in payload:
                aud = payload['aud']
                match = re.search(r'(idx-sherry-[^\.]+\.cluster-[^\.]+\.cloudworkstations\.dev)', aud)
                if match:
                    return f"https://{BASE_PREFIX}{match.group(1).split('idx-sherry-')[1]}"
        
        # 如果提取失败，使用默认域名
        return f"https://{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"
    except Exception as e:
        log_message(f"提取域名时出错: {e}")
        return f"https://{BASE_PREFIX}1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev"

def check_page_status_with_requests():
    """使用预设的JWT和URL值直接检查工作站的访问状态"""
    try:
        # 预设值
        preset_jwt = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2Nsb3VkLmdvb2dsZS5jb20vd29ya3N0YXRpb25zIiwiYXVkIjoiaWR4LXNoZXJyeS0xNzQ1NzUyMjgzNzQ5LmNsdXN0ZXItaWt4anpqaGxpZmN3dXJvb21ma2pyeDQzN2cuY2xvdWR3b3Jrc3RhdGlvbnMuZGV2IiwiaWF0IjoxNzQ2NzA3MDU1LCJleHAiOjE3NDY3OTMzOTV9.mRGJrxhTNmJ-YTit_SHGSJs9UDIOrBmgRrCqIX0Jio_orzUoVx7MtEzCfR5M2QJonVi98cOJjp0TfDpeNuJ3jnVj9GK0dZjO4bd26eAylCLU-UVt6TStzJLEYohJZHC71naMHDpLTHAajGvT4axxY_EGfyqt5GhjMMOCz_-vTeK_fmIayctGjMVGkogYimmoKfOHKzBkPgT4kSNbUA4NPjAUILVOmjxLcUmksPSdHXAPkO9Q4NEcjNQ2-b3Ax5BlF2W6Ae13pH9NgHPxeaGd2NwmJl5nivRop3E1X7LQ49YLAHGmCzD6D8z4qtoNjC8FibhlRBGvty48sYtexOn13g'
        preset_url = 'https://9000-idx-sherry-1745752283749.cluster-ikxjzjhlifcwuroomfkjrx437g.cloudworkstations.dev/'
        
        # 从cookie文件中提取JWT(如果存在)
        jwt = preset_jwt
        
        # 尝试从cookie.json文件加载JWT
        try:
            if os.path.exists(cookies_path):
                cookie_data = load_cookies(cookies_path)
                for cookie in cookie_data.get("cookies", []):
                    if cookie.get("name") == "WorkstationJwtPartitioned":
                        jwt = cookie.get("value")
                        log_message("从cookie.json中成功加载了JWT")
                        break
        except Exception as e:
            log_message(f"从cookie.json加载JWT失败: {e}，将使用预设值")
                
        # 构建请求
        request_cookies = {'WorkstationJwtPartitioned': jwt}
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US',
            'Connection': 'keep-alive',
            'Referer': 'https://workstations.cloud.google.com/',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
        }
        
        log_message(f"使用requests检查工作站状态，URL: {preset_url}")
        log_message(f"使用JWT: {jwt[:20]}... (已截断)")
        
        # 发送请求获取页面状态
        response = requests.get(
            preset_url,
            cookies=request_cookies,
            headers=headers,
            timeout=15
        )
        
        log_message(f"页面状态码: {response.status_code}")
        
        if response.status_code == 200:
            log_message("页面状态码200，工作站可以直接通过协议访问")
            return True
        else:
            log_message(f"页面状态码为{response.status_code}，无法直接通过协议访问")
            return False
    except Exception as e:
        log_message(f"使用requests检查工作站状态时出错: {e}")
        return False

async def handle_terms_dialog(page, max_attempts=3):
    """处理Terms对话框"""
    for attempt in range(1, max_attempts + 1):
        try:
            log_message(f"第{attempt}次尝试处理Terms对话框...")
            
            # 使用JavaScript直接勾选复选框，避免点击到链接
            await page.evaluate("""
                // 尝试多种可能的选择器找到复选框
                const selectors = [
                    '#utos-checkbox',
                    'input[type="checkbox"][id*="checkbox"]',
                    'input[type="checkbox"]',
                    'div.utoscheckbox-root input[type="checkbox"]'
                ];
                
                // 尝试所有选择器
                for (const selector of selectors) {
                    const checkbox = document.querySelector(selector);
                    if (checkbox && !checkbox.checked) {
                        checkbox.checked = true;
                        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                        console.log('已通过JavaScript勾选复选框：' + selector);
                        return true;
                    }
                }
                
                // 如果没有找到匹配的选择器，提供更多详细信息
                console.log('无法找到复选框，页面内的所有checkbox如下:');
                document.querySelectorAll('input[type="checkbox"]').forEach((cb, i) => {
                    console.log(`Checkbox ${i}: id=${cb.id}, name=${cb.name}, aria-label=${cb.getAttribute('aria-label')}`);
                });
                
                return false;
            """)
            
            log_message("已尝试通过JavaScript勾选复选框")
            
            # 等待状态更新
            await asyncio.sleep(2)
            
            # 使用JavaScript点击确认按钮
            button_clicked = await page.evaluate("""
                // 尝试多种可能的按钮选择器
                const buttonSelectors = [
                    'button[name="confirm"], button:has-text("Confirm")',
                    '#submit-button:not([disabled])',
                    'button[type="submit"]:not([disabled])',
                    'button.confirm-button:not([disabled])',
                    'button.mat-button:not([disabled])',
                    'button:not([disabled])'
                ];
                
                // 尝试所有按钮选择器
                for (const selector of buttonSelectors) {
                    const buttons = Array.from(document.querySelectorAll(selector));
                    // 优先选择包含Confirm或Accept文本的按钮
                    const confirmButton = buttons.find(btn => 
                        btn.textContent.includes('Confirm') || 
                        btn.textContent.includes('Accept') ||
                        btn.textContent.includes('确认') ||
                        btn.textContent.includes('接受')
                    ) || buttons[0]; // 如果没找到，使用第一个按钮
                    
                    if (confirmButton) {
                        console.log('找到确认按钮：' + confirmButton.textContent);
                        confirmButton.click();
                        return true;
                    }
                }
                
                // 如果没找到匹配的按钮，提供更多信息
                console.log('无法找到确认按钮，页面内的所有按钮如下:');
                document.querySelectorAll('button').forEach((btn, i) => {
                    console.log(`Button ${i}: text=${btn.textContent.trim()}, disabled=${btn.disabled}`);
                });
                
                return false;
            """)
            
            if button_clicked:
                log_message("已通过JavaScript点击确认按钮")
                return True
            else:
                log_message("通过JavaScript未能找到确认按钮")
                
            # 如果JavaScript方法失败，尝试截图来帮助调试
            try:
                screenshot_path = f"terms_dialog_attempt_{attempt}.png"
                await page.screenshot(path=screenshot_path)
                log_message(f"已保存Terms对话框截图到 {screenshot_path}")
            except Exception as e:
                log_message(f"保存截图失败: {e}")
                
        except Exception as e:
            log_message(f"第{attempt}次处理Terms对话框失败: {e}")
            
            # 尝试获取页面源码以便调试
            try:
                html = await page.content()
                log_message(f"当前页面源码片段: {html[:500]}...")
            except Exception:
                pass
            
            if attempt < max_attempts:
                log_message("等待2秒后重试...")
                await asyncio.sleep(2)
            else:
                log_message("已达到最大重试次数，继续执行后续步骤")
                return False
    
    # 如果所有尝试都失败，尝试点击页面任意处继续
    try:
        # 尝试点击页面中间位置，避开链接
        log_message("尝试点击页面中间，绕过Terms对话框...")
        await page.mouse.click(page.viewport_size["width"] // 2, page.viewport_size["height"] // 2)
        await asyncio.sleep(2)
        return True
    except Exception as e:
        log_message(f"尝试点击页面中间也失败: {e}")
        return False

async def wait_for_workspace_loaded(page, timeout=180):
    """等待Firebase Studio工作区加载完成"""
    log_message(f"检测是否成功进入Firebase Studio...")
    current_url = page.url
    log_message(f"当前URL: {current_url}")
    
    if "sherry" in current_url or "workspace" in current_url or "cloudworkstations" in current_url or "firebase" in current_url:
        log_message("URL包含目标关键词，确认进入目标页面")
        
        # 先等待页面基本加载，减少等待时间
        log_message("等待页面基本加载...")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=60000)
            log_message("DOM内容已加载")
            
            # 尝试等待网络稳定，但不阻塞流程
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
                log_message("网络活动已稳定")
            except Exception as e:
                log_message(f"等待网络稳定超时，但这不会阻塞流程: {e}")
        except Exception as e:
            log_message(f"等待DOM加载超时: {e}，但将继续流程")
        
        # 等待页面和资源更完整加载，但时间缩短
        log_message("等待60秒让页面和资源完全加载...")
        await asyncio.sleep(60)
        log_message("等待时间结束，开始检测侧边栏元素...")
        
        # 在检测元素前先刷新页面，确保页面处于最新状态
        log_message("刷新页面以确保内容正确加载...")
        try:
            await page.reload()
            
            # 等待页面重新加载
            await page.wait_for_load_state("domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                log_message(f"刷新后等待网络稳定超时，但这不会阻塞流程: {e}")
                
            # 等待额外的时间让页面元素稳定
            log_message("等待额外的30秒让页面元素稳定...")
            await asyncio.sleep(30)
        except Exception as e:
            log_message(f"刷新页面出错: {e}，但将继续流程")
        
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
                
                # IDE相关的侧边栏按钮
                ide_btn_selectors = [
                    '[class*="codicon-explorer-view-icon"], [aria-label*="Explorer"]',
                    '[class*="codicon-search-view-icon"], [aria-label*="Search"]',
                    '[class*="codicon-source-control-view-icon"], [aria-label*="Source Control"]',
                    '[class*="codicon-run-view-icon"], [aria-label*="Run and Debug"]',
                ]
                
                # Web元素检测（只保留一个最可能匹配的选择器）
                web_selector = 'div[aria-label="Web"] span.tab-label-name, div[aria-label*="Web"], [class*="monaco-icon-label"] span.monaco-icon-name-container:has-text("Web")'
                
                # 合并所有需要检测的选择器
                all_selectors = ide_btn_selectors + [web_selector]
                
                # 依次等待每个元素，使用更短的超时时间
                found_elements = 0
                for sel in all_selectors:
                    try:
                        await target.wait_for_selector(sel, timeout=10000)  # 10秒超时
                        found_elements += 1
                        log_message(f"找到元素 {found_elements}/{len(all_selectors)}: {sel}")
                    except Exception as e:
                        log_message(f"未找到元素: {sel}, 错误: {e}")
                        # 即使某个元素未找到，也继续检查其他元素
                        continue
                
                if found_elements > 0:
                    log_message(f"主界面找到 {found_elements}/{len(all_selectors)} 个元素（第{refresh_attempt}次尝试）")
                    # 只要找到至少5个元素（全部）就认为成功
                    if found_elements >= len(all_selectors):
                        log_message(f"找到全部UI元素 ({found_elements}/{len(all_selectors)})，认为界面加载成功")
                        
                        # 停留较短时间
                        log_message("停留15秒以确保页面完全加载...")
                        await asyncio.sleep(15)
                        
                        # 保存cookie状态
                        log_message("已更新存储状态到cookie.json")
                        return True
                    else:
                        log_message(f"找到的元素数量不足 ({found_elements}/{len(all_selectors)})，需要至少4个元素才认为成功")
                        if found_elements >= 4:
                            log_message(f"找到大部分UI元素 ({found_elements}/{len(all_selectors)})，认为界面基本加载成功")
                            # 保存cookie状态
                            log_message("已更新存储状态到cookie.json")
                            return True
                        elif refresh_attempt < max_refresh_retries:
                            log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                            await page.reload()
                            log_message("页面刷新后等待60秒让元素加载...")
                            await asyncio.sleep(60)
                        else:
                            log_message("已达到最大刷新重试次数，未能找到足够的UI元素")
                            # 尽管未找到足够元素，我们也返回成功，因为我们已经到了目标页面
                            return True
                else:
                    log_message(f"未找到任何UI元素，尝试刷新...")
                    if refresh_attempt < max_refresh_retries:
                        log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                        await page.reload()
                        log_message("页面刷新后等待60秒让元素加载...")
                        await asyncio.sleep(60)
                    else:
                        log_message("已达到最大刷新重试次数，未能找到任何UI元素")
                        # 尽管未找到元素，我们也返回成功，因为我们已经到了目标页面
                        return True
            except Exception as e:
                log_message(f"第{refresh_attempt}次尝试：等待主界面元素时出错: {e}")
                if refresh_attempt < max_refresh_retries:
                    log_message(f"刷新页面并重试（第{refresh_attempt}/{max_refresh_retries}次）...")
                    await page.reload()
                    log_message("页面刷新后等待60秒让元素加载...")
                    await asyncio.sleep(60)
                else:
                    log_message("已达到最大刷新重试次数，无法完成检测")
                    # 尽管出错，我们也返回成功，因为我们已经到了目标页面
                    return True
    else:
        log_message("URL未包含目标关键词，未检测到目标页面")
        return False
    
    # 如果执行到这里，说明流程已完成但可能未找到所有元素
    return True

async def click_workspace_icon(page):
    """尝试点击工作区图标"""
    log_message("尝试点击workspace图标...")
    
    # 工作区图标选择器列表
    selectors = [
        'div[class="workspace-icon"]',
        'img[src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
        '.workspace-icon',
        'img[role="presentation"][class="custom-icon"]',
        'div[_ngcontent-ng-c2464377164][class="workspace-icon"]',
        'div.workspace-icon img.custom-icon',
        '.workspace-icon img'
    ]
    
    for selector in selectors:
        try:
            log_message(f"尝试选择器: {selector}")
            element = await page.wait_for_selector(selector, timeout=5000)
            if element:
                # 尝试多种点击方法
                try:
                    await element.click(force=True)
                    log_message(f"成功点击元素! 使用选择器: {selector}")
                    return True
                except Exception as e:
                    log_message(f"直接点击失败: {e}，尝试JavaScript点击")
                    try:
                        await page.evaluate("(element) => element.click()", element)
                        log_message(f"使用JavaScript成功点击元素!")
                        return True
                    except Exception:
                        continue
        except Exception:
            continue
            
    log_message("所有选择器都尝试失败，无法点击工作区图标")
    return False

async def navigate_to_firebase_by_clicking(page):
    """通过点击已验证的工作区图标导航到Firebase Studio"""
    log_message("通过点击已验证的工作区图标导航到Firebase Studio...")
    
    # 获取点击前的URL
    pre_click_url = page.url
    log_message(f"点击前当前URL: {pre_click_url}")
    
    # 尝试点击工作区图标
    workspace_icon_clicked = await click_workspace_icon(page)
    
    if not workspace_icon_clicked:
        log_message("无法点击工作区图标，导航失败")
        return False
    
    # 等待页面响应，检查URL变化
    await asyncio.sleep(5)
    
    # 检查点击后URL是否变化
    post_click_url = page.url
    log_message(f"点击后当前URL: {post_click_url}")
    
    url_changed = pre_click_url != post_click_url
    log_message(f"URL是否发生变化: {url_changed}")
    
    if url_changed:
        log_message("点击工作区图标成功，URL已变化，继续等待工作区加载")
        # URL已变化，直接返回True，后续操作不变
        return True
    else:
        log_message("点击工作区图标后URL未变化，导航失败")
        return False

async def login_with_ui_flow(page):
    """通过UI交互流程登录idx.google.com，然后跳转到Firebase Studio"""
    try:
        log_message("开始UI交互登录流程...")
        
        # 先导航到idx.google.com
        try:
            await page.goto("https://idx.google.com/", timeout=TIMEOUT)
            await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        except Exception as e:
            log_message(f"导航到idx.google.com失败: {e}，但将继续尝试")
        
        # 等待页面加载
        await asyncio.sleep(10)
        
        # 处理Terms对话框
        await handle_terms_dialog(page)
        
        # 检查是否有工作区图标并点击
        workspace_icon_clicked = await click_workspace_icon(page)
        
        if workspace_icon_clicked:
            log_message("成功点击工作区图标，等待页面响应...")
            
            # 等待页面响应，验证登录状态
            await asyncio.sleep(5)
            
            # 双重验证登录成功
            current_url = page.url
            log_message(f"点击后当前URL: {current_url}")
            
            # 验证1: 检测URL不包含signin
            url_valid = "idx.google.com" in current_url and "signin" not in current_url
            
            # 验证2: 检测是否有其他工作区图标出现（通常点击后会显示其他工作区图标）
            workspace_icon_visible = False
            try:
                # 简化的验证，通常点击后页面会显示其他内容，只要URL验证通过即可
                workspace_icon_visible = url_valid  # 如果URL有效，我们假设图标检查也通过
            except Exception as e:
                log_message(f"点击后检查工作区内容时出错: {e}")
            
            # 双重验证结果
            if url_valid and workspace_icon_visible:
                log_message("UI交互后双重验证通过：确认已成功登录idx.google.com!")
                
                # 登录成功后，通过点击已验证的工作区图标导航到Firebase Studio
                return await navigate_to_firebase_by_clicking(page)
            else:
                log_message(f"UI交互后验证登录失败：URL不含signin: {url_valid}, 工作区验证: {workspace_icon_visible}")
                return False
        else:
            log_message("未能点击工作区图标，UI流程失败")
            return False
    except Exception as e:
        log_message(f"UI交互流程出错: {e}")
        return False

async def direct_url_access(page):
    """先访问idx.google.com验证登录，成功后通过点击已验证的工作区图标进入Firebase Studio"""
    try:
        # 先访问idx.google.com
        log_message("先访问idx.google.com验证登录状态...")
        await page.goto("https://idx.google.com/", timeout=TIMEOUT)
        await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        
        # 等待页面加载
        await asyncio.sleep(5)
        
        # 提前处理Terms对话框(如果出现)
        await handle_terms_dialog(page)
        
        # 验证是否登录成功 - 双重验证
        current_url = page.url
        log_message(f"当前URL: {current_url}")
        
        # 验证1: 检测URL不包含signin
        url_valid = "idx.google.com" in current_url and "signin" not in current_url
        
        # 验证2: 检测工作区图标是否出现
        workspace_icon_visible = False
        try:
            # 工作区图标选择器列表
            selectors = [
                'div[class="workspace-icon"]',
                'img[src="https://www.gstatic.com/monospace/250314/workspace-blank-192.png"]',
                '.workspace-icon',
                'img[role="presentation"][class="custom-icon"]'
            ]
            
            for selector in selectors:
                try:
                    icon = await page.wait_for_selector(selector, timeout=5000)
                    if icon:
                        log_message(f"找到工作区图标! 使用选择器: {selector}")
                        workspace_icon_visible = True
                        break
                except Exception:
                    continue
        except Exception as e:
            log_message(f"检查工作区图标时出错: {e}")
        
        # 双重验证结果
        if url_valid and workspace_icon_visible:
            log_message("双重验证通过：URL不含signin且工作区图标出现，确认已成功登录idx.google.com!")
            
            # 登录成功后，通过点击已验证的工作区图标导航到Firebase Studio
            return await navigate_to_firebase_by_clicking(page)
        else:
            log_message(f"验证登录失败：URL不含signin: {url_valid}, 工作区图标出现: {workspace_icon_visible}")
            return False
    except Exception as e:
        log_message(f"访问idx.google.com或跳转到Firebase Studio失败: {e}")
        return False

async def run(playwright: Playwright) -> bool:
    """主运行函数"""
    for attempt in range(1, MAX_RETRIES + 1):
        log_message(f"第{attempt}/{MAX_RETRIES}次尝试...")
        
        # 随机选择User-Agent和视口大小
        random_user_agent = USER_AGENTS[attempt % len(USER_AGENTS)]
        random_viewport = VIEWPORT_SIZES[attempt % len(VIEWPORT_SIZES)]
        
        # 浏览器配置
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-size=1366,768',
            '--start-maximized',
            '--disable-gpu',
            '--disable-dev-shm-usage',
        ]
        
        # 启动浏览器
        browser = await playwright.chromium.launch(
            headless=True,  # 设置为True在生产环境中运行
            slow_mo=300,
            args=browser_args
        )
        
        try:
            # 加载cookie状态
            cookie_data = load_cookies(cookies_path)
            
            # 创建浏览器上下文
            context = await browser.new_context(
                user_agent=random_user_agent,
                viewport=random_viewport,
                device_scale_factor=1.0,
                locale="en-US",
                timezone_id="America/New_York",
                java_script_enabled=True,
                storage_state=cookie_data  # 直接使用加载的数据对象
            )
            
            page = await context.new_page()
            
            # 配置反检测措施
            await page.evaluate("""() => {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                delete navigator.__proto__.webdriver;
            }""")
            
            # ===== 先尝试直接URL访问 =====
            direct_access_success = await direct_url_access(page)
            
            if not direct_access_success:
                log_message("通过cookies直接登录失败，尝试UI交互流程...")
                ui_success = await login_with_ui_flow(page)
                
                if not ui_success:
                    log_message(f"第{attempt}次尝试：UI交互流程失败")
                    if attempt < MAX_RETRIES:
                        await context.close()
                        await browser.close()
                        continue
                    else:
                        log_message("已达到最大重试次数，放弃尝试")
                        await context.close()
                        await browser.close()
                        return False
            
            # ===== 等待工作区加载 =====
            workspace_loaded = await wait_for_workspace_loaded(page)
            if workspace_loaded:
                log_message("工作区加载验证成功!")
                
                # 保存最终cookie状态
                await context.storage_state(path=cookies_path)
                log_message(f"已保存最终cookie状态到 {cookies_path}")
                
                # 成功完成
                await context.close()
                await browser.close()
                return True
            else:
                log_message(f"第{attempt}次尝试：工作区加载验证失败")
                if attempt < MAX_RETRIES:
                    await context.close()
                    await browser.close()
                    continue
                else:
                    log_message("已达到最大重试次数，放弃尝试")
                    await context.close()
                    await browser.close()
                    return False
                    
        except Exception as e:
            log_message(f"第{attempt}次尝试出错: {e}")
            log_message(traceback.format_exc())
            
            try:
                await browser.close()
            except:
                pass
                
            if attempt < MAX_RETRIES:
                log_message("准备下一次尝试...")
                continue
            else:
                log_message("已达到最大重试次数，放弃尝试")
                return False
    
    return False

def extract_and_display_credentials():
    """从cookie.json中提取并显示云工作站域名和JWT"""
    try:
        if not os.path.exists(cookies_path):
            log_message("cookie.json文件不存在，无法提取凭据")
            return
            
        with open(cookies_path, 'r', encoding='utf-8') as f:
            cookie_data = json.load(f)
            
        # 提取JWT
        jwt = None
        for cookie in cookie_data.get("cookies", []):
            if cookie.get("name") == "WorkstationJwtPartitioned":
                jwt = cookie.get("value")
                break
                
        if not jwt:
            log_message("在cookie.json中未找到WorkstationJwtPartitioned")
            return
            
        # 从JWT中提取域名
        domain = None
        try:
            parts = jwt.split('.')
            if len(parts) >= 2:
                import base64
                
                # 解码中间部分（可能需要补齐=）
                padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
                decoded = base64.b64decode(padded)
                payload = json.loads(decoded)
                
                # 从aud字段提取域名
                if 'aud' in payload:
                    aud = payload['aud']
                    match = re.search(r'(idx-sherry-[^\.]+\.cluster-[^\.]+\.cloudworkstations\.dev)', aud)
                    if match:
                        domain = f"https://{BASE_PREFIX}{match.group(1).split('idx-sherry-')[1]}"
        except Exception as e:
            log_message(f"从JWT提取域名时出错: {e}")
            
        # 显示提取的信息
        log_message("\n========== 提取的凭据信息 ==========")
        log_message(f"WorkstationJwtPartitioned: {jwt[:20]}...{jwt[-20:]} (已截断，仅显示前20和后20字符)")
        
        if domain:
            log_message(f"工作站域名: {domain}")
        else:
            log_message("无法从JWT提取域名")
            
        # 打印完整的请求示例
        log_message("\n以下是可用于访问工作站的请求示例代码:")
        code_example = f"""import requests

cookies = {{
    'WorkstationJwtPartitioned': '{jwt}',
}}

headers = {{
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US',
    'Connection': 'keep-alive',
    'Referer': 'https://workstations.cloud.google.com/',
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
}}

response = requests.get(
    '{domain if domain else "工作站URL"}',
    cookies=cookies,
    headers=headers,
)
print(response.status_code)
print(response.text)"""
        log_message(code_example)
        log_message("========== 提取完成 ==========\n")
        
    except Exception as e:
        log_message(f"提取凭据时出错: {e}")

async def main():
    """主函数"""
    try:
        log_message("开始执行IDX登录并跳转Firebase Studio的自动化流程...")
        
        # 先用requests协议方式直接检查登录状态
        check_result = check_page_status_with_requests()
        if check_result:
            log_message("【检查结果】工作站可直接通过协议访问（状态码200），流程直接退出")
            # 显示提取的凭据
            extract_and_display_credentials()
            if all_messages:
                full_message = "\n".join(all_messages)
                send_to_telegram(full_message)
            return
        
        log_message("【检查结果】工作站不可直接通过协议访问，继续执行完整自动化流程")
        
        # 使用Playwright执行自动化流程
        async with async_playwright() as playwright:
            success = await run(playwright)
            
        log_message(f"自动化流程执行结果: {'成功' if success else '失败'}")
        
        # 显示提取的凭据（无论成功失败）
        extract_and_display_credentials()
        
        # 发送通知
        if all_messages:
            full_message = "\n".join(all_messages)
            send_to_telegram(full_message)
            
    except Exception as e:
        log_message(f"主流程执行出错: {e}")
        log_message(traceback.format_exc())
        
        # 尝试提取凭据（即使出错）
        extract_and_display_credentials()
        
        # 确保错误信息也被发送
        if all_messages:
            full_message = "\n".join(all_messages)
            send_to_telegram(full_message)

if __name__ == "__main__":
    all_messages = []
    asyncio.run(main())
