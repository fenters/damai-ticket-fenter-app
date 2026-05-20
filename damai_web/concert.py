# -*- coding: utf-8 -*-
"""
大麦网 Web 端抢票模块（Selenium）
提供页面分析和抢票功能，供 GUI 和 CLI 使用
"""

import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains


class PageAnalyzer:
    """页面分析器 - 专门用于分析大麦网演出页面信息"""
    
    def __init__(self, driver, log_callback=None):
        self.driver = driver
        self.log = log_callback or (lambda x: print(x))
    
    def analyze_show_page(self, url):
        """分析演出页面，提取城市、日期、价格等信息"""
        try:
            self.log(f"🔍 正在访问页面: {url}")
            self.driver.get(url)
            
            # 等待页面加载
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "perform__order__select"))
            )
            
            # 提取演出基本信息
            page_info = self._extract_basic_info()
            
            # 提取选择项信息
            page_info.update(self._extract_selection_options())
            
            self.log(f"✅ 页面分析完成，找到 {len(page_info.get('cities', []))} 个城市，{len(page_info.get('dates', []))} 个日期，{len(page_info.get('prices', []))} 个价格")
            
            return page_info
            
        except Exception as e:
            self.log(f"❌ 页面分析失败: {e}")
            return None
    
    def _extract_basic_info(self):
        """提取基本信息"""
        info = {
            "title": "未知演出",
            "venue": "未知场地", 
            "status": "未知状态",
            "cities": [],
            "dates": [],
            "prices": []
        }
        
        try:
            # 演出标题
            title_elem = self.driver.find_element(By.CSS_SELECTOR, ".perform__order__title h1")
            info["title"] = title_elem.text.strip()
        except:
            pass
            
        try:
            # 演出场地
            venue_elem = self.driver.find_element(By.CSS_SELECTOR, ".perform__order__venue")
            info["venue"] = venue_elem.text.strip()
        except:
            pass
            
        try:
            # 售票状态
            status_elem = self.driver.find_element(By.CSS_SELECTOR, ".perform__order__price")
            info["status"] = status_elem.text.strip()
        except:
            pass
            
        return info
    
    def _extract_selection_options(self):
        """提取选择项（城市、日期、价格）"""
        options = {
            "cities": [],
            "dates": [],
            "prices": []
        }
        
        try:
            # 查找所有选择框
            select_boxes = self.driver.find_elements(By.CSS_SELECTOR, ".perform__order__select")
            
            for box in select_boxes:
                try:
                    # 获取选择框标题来判断类型
                    title_elem = box.find_element(By.CSS_SELECTOR, ".select_left")
                    title = title_elem.text.strip()
                    
                    # 获取选项列表
                    option_elems = box.find_elements(By.CSS_SELECTOR, ".select_right .select_right_list_item")
                    option_texts = []
                    
                    for opt in option_elems:
                        # 跳过禁用的选项
                        if "disabled" in opt.get_attribute("class"):
                            continue
                        text = opt.text.strip()
                        if text:
                            option_texts.append(text)
                    
                    # 根据标题判断选项类型
                    if "城市" in title or "地区" in title:
                        options["cities"] = option_texts
                    elif "日期" in title or "时间" in title or "场次" in title:
                        options["dates"] = option_texts
                    elif "价格" in title or "票档" in title:
                        options["prices"] = option_texts
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.log(f"⚠️ 选择项提取部分失败: {e}")
            
        return options


class WebConcert:
    """Web端抢票类"""
    
    def __init__(self, driver, config, log_callback=None, cookie_callback=None, stop_check=None):
        self.driver = driver
        self.config = config
        self.log = log_callback or (lambda x: print(x))
        self.save_cookie = cookie_callback or (lambda: None)  # Cookie保存回调
        self.should_stop = stop_check or (lambda: False)  # 停止检查回调
        
    def choose_ticket(self):
        """执行完整的抢票流程（带循环等待）"""
        try:
            # 访问目标页面
            self.log(f"🎯 前往演出页面: {self.config['target_url']}")
            self.driver.get(self.config['target_url'])
            
            # 页面加载后保存cookie
            self.save_cookie()
            
            # 等待页面加载
            self._wait_for_page_load()
            
            # 选择城市
            if self.config.get('city'):
                self._select_city(self.config['city'])
                
            # 选择日期
            if self.config.get('date'):
                self._select_date(self.config['date'])
                
            # 选择价格
            if self.config.get('price'):
                self._select_price(self.config['price'])
                
            # 开始循环等待购买
            self._start_ticket_loop()
            
        except Exception as e:
            self.log(f"❌ 抢票过程出错: {e}")
            raise
    
    def _start_ticket_loop(self):
        """开始循环等待抢票"""
        self.log("🔄 开始循环等待抢票...")
        loop_count = 0
        
        while not self.should_stop():  # 检查停止标志
            try:
                loop_count += 1
                self.log(f"🔄 第 {loop_count} 次尝试...")
                
                # 检查购买按钮状态
                button_status = self._check_buy_button_status()
                
                if button_status == "available":
                    self.log("✅ 发现可购买，开始抢票！")
                    self._click_buy_button()
                    self._handle_purchase_page()
                    break  # 成功进入购买页面，退出循环
                    
                elif button_status == "not_started":
                    self.log("⏳ 抢票未开始，等待中...")
                    time.sleep(2)  # 等待2秒后重试
                    
                elif button_status == "sold_out":
                    if self.config.get('if_listen', False):
                        self.log("📋 已售罄，启用回流监听...")
                        time.sleep(5)  # 回流监听间隔稍长
                    else:
                        self.log("❌ 已售罄且未启用回流监听")
                        break
                        
                else:
                    self.log("🔄 未知状态，刷新页面重试...")
                    self.driver.refresh()
                    time.sleep(3)
                    
                # 每隔一定次数刷新页面，防止页面超时
                if loop_count % 10 == 0:
                    self.log("🔄 定期刷新页面...")
                    self.driver.refresh()
                    time.sleep(2)
                    self._wait_for_page_load()
                    
            except Exception as e:
                self.log(f"⚠️ 循环中出现异常: {e}")
                time.sleep(1)
                continue
                
        if self.should_stop():
            self.log("⏹ 用户停止了抢票")
                
    def _check_buy_button_status(self):
        """检查购买按钮状态"""
        try:
            # 检查各种可能的按钮文本
            button_texts = {
                "提交缺货登记": "not_started",
                "缺货登记": "sold_out", 
                "立即购票": "available",
                "立即购买": "available",
                "立即预订": "available",
                "不，立即购票": "available",
                "不，立即预订": "available",
                "马上购买": "available",
                "马上预订": "available"
            }
            
            # 尝试CSS选择器查找
            buy_selectors = [
                ".buy-link",
                ".buybtn", 
                ".buy-btn",
                "[data-spm='dbuy']",
                "button[class*='buy']",
                ".perform__order__buy"
            ]
            
            for selector in buy_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            text = element.text.strip()
                            if text in button_texts:
                                return button_texts[text]
                except:
                    continue
                    
            # 尝试文本查找
            for text, status in button_texts.items():
                try:
                    elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
                    if elements and elements[0].is_displayed():
                        return status
                except:
                    continue
                    
            return "unknown"
            
        except Exception as e:
            self.log(f"⚠️ 检查按钮状态失败: {e}")
            return "unknown"
    
    def _wait_for_page_load(self):
        """等待页面加载完成"""
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "perform__order__select"))
            )
            self.log("✅ 页面加载完成")
        except TimeoutException:
            self.log("⚠️ 页面加载超时，继续执行")
    
    def _select_city(self, target_city):
        """选择城市"""
        try:
            self.log(f"🏙️ 正在选择城市: {target_city}")
            
            # 查找城市选择框
            city_boxes = self.driver.find_elements(By.CSS_SELECTOR, ".perform__order__select")
            
            for box in city_boxes:
                try:
                    title = box.find_element(By.CSS_SELECTOR, ".select_left").text
                    if "城市" in title or "地区" in title:
                        # 点击展开选项
                        box.click()
                        time.sleep(0.5)
                        
                        # 查找匹配的城市选项
                        options = box.find_elements(By.CSS_SELECTOR, ".select_right_list_item")
                        for option in options:
                            if target_city in option.text:
                                option.click()
                                self.log(f"✅ 已选择城市: {target_city}")
                                time.sleep(1)
                                return
                        break
                except:
                    continue
                    
            self.log(f"⚠️ 未找到城市选项: {target_city}")
            
        except Exception as e:
            self.log(f"❌ 选择城市失败: {e}")
    
    def _select_date(self, target_date):
        """选择日期"""
        try:
            self.log(f"📅 正在选择日期: {target_date}")
            
            # 查找日期选择框
            date_boxes = self.driver.find_elements(By.CSS_SELECTOR, ".perform__order__select")
            
            for box in date_boxes:
                try:
                    title = box.find_element(By.CSS_SELECTOR, ".select_left").text
                    if "日期" in title or "时间" in title or "场次" in title:
                        # 点击展开选项
                        box.click()
                        time.sleep(0.5)
                        
                        # 查找匹配的日期选项
                        options = box.find_elements(By.CSS_SELECTOR, ".select_right_list_item")
                        for option in options:
                            if target_date in option.text:
                                option.click()
                                self.log(f"✅ 已选择日期: {target_date}")
                                time.sleep(1)
                                return
                        break
                except:
                    continue
                    
            self.log(f"⚠️ 未找到日期选项: {target_date}")
            
        except Exception as e:
            self.log(f"❌ 选择日期失败: {e}")
    
    def _select_price(self, target_price):
        """选择价格"""
        try:
            self.log(f"💰 正在选择价格: {target_price}")
            
            # 查找价格选择框
            price_boxes = self.driver.find_elements(By.CSS_SELECTOR, ".perform__order__select")
            
            for box in price_boxes:
                try:
                    title = box.find_element(By.CSS_SELECTOR, ".select_left").text
                    if "价格" in title or "票档" in title:
                        # 点击展开选项
                        box.click()
                        time.sleep(0.5)
                        
                        # 查找匹配的价格选项
                        options = box.find_elements(By.CSS_SELECTOR, ".select_right_list_item")
                        for option in options:
                            if target_price in option.text:
                                option.click()
                                self.log(f"✅ 已选择价格: {target_price}")
                                time.sleep(1)
                                return
                        break
                except:
                    continue
                    
            self.log(f"⚠️ 未找到价格选项: {target_price}")
            
        except Exception as e:
            self.log(f"❌ 选择价格失败: {e}")
    
    def _click_buy_button(self):
        """点击立即购买按钮"""
        try:
            self.log("🎫 正在点击立即购买/预订...")
            
            # 多种可能的购买按钮选择器
            buy_selectors = [
                ".buy-link",
                ".buybtn",
                ".buy-btn", 
                "[data-spm='dbuy']",
                "button[class*='buy']",
                ".perform__order__buy",
                "[data-spm-anchor-id*='project']"
            ]
            
            # 先尝试CSS选择器
            for selector in buy_selectors:
                try:
                    buy_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    buy_btn.click()
                    self.log("✅ 已点击购买/预订按钮")
                    time.sleep(2)
                    return
                except:
                    continue
                    
            # 如果CSS选择器都失败，尝试通过文本内容查找
            text_selectors = [
                "立即购票",
                "立即购买", 
                "立即预订",
                "马上购买",
                "马上预订",
                "不，立即购票",
                "不，立即预订"
            ]
            
            for text in text_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            element.click()
                            self.log(f"✅ 已点击购买/预订按钮 (文本: {text})")
                            time.sleep(2)
                            return
                except:
                    continue
                    
            # JavaScript fallback
            try:
                self.log("🔄 尝试JavaScript方式点击购买按钮...")
                js_script = """
                var buyTexts = ['立即购票', '立即购买', '立即预订', '马上购买', '马上预订', '不，立即购票', '不，立即预订'];
                var buySelectors = ['.buy-link', '.buybtn', '.buy-btn', '[data-spm="dbuy"]', 'button[class*="buy"]', '.perform__order__buy'];
                
                for (var i = 0; i < buySelectors.length; i++) {
                    var elements = document.querySelectorAll(buySelectors[i]);
                    for (var j = 0; j < elements.length; j++) {
                        if (elements[j].offsetWidth > 0 && elements[j].offsetHeight > 0) {
                            elements[j].click();
                            return true;
                        }
                    }
                }
                
                for (var i = 0; i < buyTexts.length; i++) {
                    var elements = document.querySelectorAll('*');
                    for (var j = 0; j < elements.length; j++) {
                        if (elements[j].textContent && elements[j].textContent.trim() === buyTexts[i]) {
                            if (elements[j].offsetWidth > 0 && elements[j].offsetHeight > 0) {
                                elements[j].click();
                                return true;
                            }
                        }
                    }
                }
                
                return false;
                """
                
                result = self.driver.execute_script(js_script)
                if result:
                    self.log("✅ 通过JavaScript成功点击购买/预订按钮")
                    time.sleep(2)
                    return
                    
            except Exception as e:
                self.log(f"⚠️ JavaScript点击失败: {e}")
                    
            self.log("❌ 未找到购买/预订按钮")
            
        except Exception as e:
            self.log(f"❌ 点击购买/预订按钮失败: {e}")
    
    def _handle_purchase_page(self):
        """处理购买页面（选择观演人、确认等）"""
        try:
            self.log("📋 处理购买页面...")
            
            time.sleep(3)
            
            self._select_viewers()
            
            self._handle_popups()
            
            if self.config.get('if_commit_order', False):
                self._submit_order()
            else:
                self.log("ℹ️ 未开启自动提交，请手动完成后续操作")
                
        except Exception as e:
            self.log(f"❌ 购买页面处理失败: {e}")
    
    def _select_viewers(self):
        """选择观演人"""
        try:
            self.log("👥 正在选择观演人...")
            
            viewer_selectors = [
                "#dmViewerBlock_DmViewerBlock",
                ".viewer",
                ".viwer-info-name",
                "[class*='viewer']",
                "[id*='dmViewerBlock']",
                ".buyer-list", 
                ".viewer-list",
                "[class*='buyer']",
                "[class*='audience']"
            ]
            
            found_viewers = False
            
            for selector in viewer_selectors:
                try:
                    viewer_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if viewer_elements:
                        self.log(f"找到观演人区域: {selector}")
                        found_viewers = True
                        break
                except:
                    continue
            
            if not found_viewers:
                self.log("⚠️ 未找到观演人选择区域")
                return
            
            clickable_selectors = [
                ".icondanxuan-xuanzhong_",
                "[class*='icondanxuan']",
                "i.iconfont",
                ".viwer-info-name",
                ".viewer div[style*='display: flex']",
                "input[type='checkbox']",
                "label",
                "[role='checkbox']"
            ]
            
            selected_count = 0
            
            for selector in clickable_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.3)
                                
                                element.click()
                                selected_count += 1
                                self.log(f"✅ 已选择观演人 ({selected_count})")
                                time.sleep(0.5)
                                
                                if selected_count >= 1:
                                    self.log("✅ 观演人选择完成 (已选择1位)")
                                    return
                                    
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    continue
            
            if selected_count == 0:
                self.log("🔄 尝试通过JavaScript选择观演人...")
                try:
                    js_script = """
                    var viewers = document.querySelectorAll('.viewer, .viwer-info-name, [class*="viewer"], [id*="dmViewerBlock"]');
                    var selected = false;
                    
                    for (var i = 0; i < viewers.length && !selected; i++) {
                        var element = viewers[i];
                        if (element.offsetWidth > 0 && element.offsetHeight > 0) {
                            element.click();
                            selected = true;
                        }
                    }
                    
                    if (!selected) {
                        var icons = document.querySelectorAll('i.iconfont, [class*="icon"]');
                        for (var j = 0; j < icons.length && !selected; j++) {
                            if (icons[j].offsetWidth > 0 && icons[j].offsetHeight > 0) {
                                icons[j].click();
                                selected = true;
                            }
                        }
                    }
                    
                    return selected;
                    """
                    
                    result = self.driver.execute_script(js_script)
                    if result:
                        self.log("✅ 通过JavaScript成功选择观演人")
                    else:
                        self.log("⚠️ JavaScript选择也未成功")
                        
                except Exception as e:
                    self.log(f"⚠️ JavaScript选择失败: {e}")
            
            if selected_count == 0:
                self.log("ℹ️ 未能自动选择观演人，可能需要手动操作")
            
        except Exception as e:
            self.log(f"⚠️ 观演人选择异常: {e}")
    
    def _handle_popups(self):
        """处理各种弹窗"""
        try:
            popup_selectors = [
                ".ant-modal-close",
                ".modal-close",
                ".dialog-close",
                "[aria-label='Close']"
            ]
            
            for selector in popup_selectors:
                try:
                    close_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if close_btn.is_displayed():
                        close_btn.click()
                        self.log("✅ 已关闭弹窗")
                        time.sleep(0.5)
                except:
                    continue
                    
        except Exception as e:
            self.log(f"⚠️ 弹窗处理异常: {e}")
    
    def _submit_order(self):
        """提交订单"""
        try:
            self.log("📄 正在提交订单...")
            
            submit_selectors = [
                "span[style*='line-height: 40px']",
                "span:contains('立即提交')",
                "[style*='line-height: 40px']",
                "//*[contains(text(), '立即提交')]",
                "//*[contains(text(), '提交订单')]",
                "//*[contains(text(), '确认购买')]",
                "//*[contains(text(), '立即支付')]",
                ".submit-btn",
                ".confirm-btn", 
                "button[class*='submit']",
                "button[class*='confirm']",
                "[role='button'][class*='submit']"
            ]
            
            for selector in submit_selectors:
                try:
                    if selector.startswith("//"):
                        continue
                    
                    submit_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in submit_elements:
                        if element.is_displayed() and element.is_enabled():
                            text = element.text.strip()
                            if any(keyword in text for keyword in ['立即提交', '提交订单', '确认购买', '立即支付']):
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.5)
                                
                                element.click()
                                self.log("✅ 订单已提交")
                                return
                                
                except Exception as e:
                    continue
            
            xpath_selectors = [
                "//*[contains(text(), '立即提交')]",
                "//*[contains(text(), '提交订单')]",
                "//*[contains(text(), '确认购买')]",
                "//*[contains(text(), '立即支付')]"
            ]
            
            for selector in xpath_selectors:
                try:
                    submit_elements = self.driver.find_elements(By.XPATH, selector)
                    for element in submit_elements:
                        if element.is_displayed() and element.is_enabled():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(0.5)
                            
                            element.click()
                            self.log("✅ 订单已提交 (通过XPath)")
                            return
                            
                except Exception as e:
                    continue
            
            self.log("🔄 尝试通过JavaScript提交订单...")
            try:
                js_script = """
                var submitTexts = ['立即提交', '提交订单', '确认购买', '立即支付'];
                var allElements = document.querySelectorAll('*');
                var submitted = false;
                
                for (var i = 0; i < allElements.length && !submitted; i++) {
                    var element = allElements[i];
                    var text = element.textContent || element.innerText || '';
                    
                    for (var j = 0; j < submitTexts.length; j++) {
                        if (text.includes(submitTexts[j]) && 
                            element.offsetWidth > 0 && 
                            element.offsetHeight > 0) {
                            
                            try {
                                element.click();
                                submitted = true;
                                break;
                            } catch (e) {
                                try {
                                    element.parentElement.click();
                                    submitted = true;
                                    break;
                                } catch (e2) {
                                    continue;
                                }
                            }
                        }
                    }
                }
                
                return submitted;
                """
                
                result = self.driver.execute_script(js_script)
                if result:
                    self.log("✅ 通过JavaScript成功提交订单")
                    return
                    
            except Exception as e:
                self.log(f"⚠️ JavaScript提交失败: {e}")
            
            self.log("⚠️ 未找到提交按钮，请手动完成提交")
            
        except Exception as e:
            self.log(f"❌ 订单提交失败: {e}")
