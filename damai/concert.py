# -*- coding: UTF-8 -*-
"""
__Author__ = "WECENG"
__Version__ = "1.0.0"
__Description__ = ""
__Created__ = 2023/10/10 17:00
"""

import os.path
import pickle
import time
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By


class Concert:
    def __init__(self, config):
        self.config = config
        self.status = 0  # 状态,表示如今进行到何种程度
        self.login_method = 1  # {0:模拟登录,1:Cookie登录}自行选择登录方式
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        self.driver = webdriver.Chrome(options=chrome_options)  # 默认Chrome浏览器

    def set_cookie(self):
        """
        :return: 写入cookie
        """
        self.driver.get(self.config.index_url)
        print("***请点击登录***\n")
        # 更新标题检测逻辑，适配新版大麦网
        while self.driver.title.find('大麦网') != -1 and self.driver.title.find('登录') == -1:
            sleep(1)
        print("***请扫码登录***\n")
        # 更新登录成功检测逻辑
        while '登录' in self.driver.title or self.driver.title.find('大麦网') == -1:
            sleep(1)
        print("***扫码成功***\n")

        # 将cookie写入damai_cookies.pkl文件中
        pickle.dump(self.driver.get_cookies(), open("damai_cookies.pkl", "wb"))
        print("***Cookie保存成功***")
        # 读取抢票目标页面
        self.driver.get(self.config.target_url)
    
    def handle_popups(self):
        """处理各种弹窗"""
        try:
            # 处理实名制提醒弹窗
            self.handle_realname_popup()
            
            # 处理其他可能的弹窗
            self.handle_general_popups()
            
        except Exception as e:
            print(f"处理弹窗时出错: {e}")
    
    def handle_realname_popup(self):
        """处理实名制提醒弹窗"""
        try:
            # 检查实名制弹窗是否存在
            popup_selectors = [
                "div.realname-popup-wrap",
                ".realname-popup-wrap",
                "[class*='realname-popup']"
            ]
            
            for selector in popup_selectors:
                popup_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if popup_elements:
                    popup = popup_elements[0]
                    if popup.is_displayed():
                        print("发现实名制提醒弹窗，正在关闭...")
                        
                        # 尝试找到"知道了"按钮并点击
                        know_button_selectors = [
                            "//div[contains(@class, 'button') and text()='知道了']",
                            "//div[contains(@class, 'operate')]//div[contains(@class, 'button') and not(contains(text(), '预填'))]"
                        ]
                        
                        button_found = False
                        for button_selector in know_button_selectors:
                            try:
                                buttons = self.driver.find_elements(By.XPATH, button_selector)
                                if buttons:
                                    button = buttons[0]
                                    if button.is_displayed() and button.is_enabled():
                                        button.click()
                                        print("成功关闭实名制提醒弹窗")
                                        time.sleep(1)
                                        button_found = True
                                        break
                            except:
                                continue
                        
                        # 如果通过选择器找不到，尝试在弹窗内查找包含"知道了"文本的元素
                        if not button_found:
                            try:
                                all_buttons = popup.find_elements(By.TAG_NAME, "div")
                                for btn in all_buttons:
                                    if btn.text.strip() == "知道了" and btn.is_displayed():
                                        btn.click()
                                        print("通过文本匹配成功关闭实名制提醒弹窗")
                                        time.sleep(1)
                                        button_found = True
                                        break
                            except:
                                pass
                        
                        # 如果还是找不到，尝试点击背景关闭
                        if not button_found:
                            try:
                                bg_elements = popup.find_elements(By.CLASS_NAME, "bg")
                                if bg_elements:
                                    bg_elements[0].click()
                                    print("通过点击背景关闭实名制提醒弹窗")
                                    time.sleep(1)
                            except:
                                pass
                        
                        break
                        
        except Exception as e:
            print(f"处理实名制弹窗时出错: {e}")
    
    def handle_general_popups(self):
        """处理其他通用弹窗"""
        try:
            # 通用弹窗关闭按钮选择器
            close_selectors = [
                "//div[contains(text(), '知道了')]",
                "//button[contains(text(), '知道了')]",
                "//div[contains(text(), '确定')]",
                "//button[contains(text(), '确定')]"
            ]
            
            for selector in close_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            # 检查元素是否在弹窗容器内
                            parent_classes = element.find_element(By.XPATH, "../..").get_attribute("class") or ""
                            if any(keyword in parent_classes.lower() for keyword in ["popup", "modal", "dialog", "overlay"]):
                                element.click()
                                print(f"关闭弹窗: {selector}")
                                time.sleep(1)
                                return
                except:
                    continue
                    
        except Exception as e:
            print(f"处理通用弹窗时出错: {e}")

    def get_cookie(self):
        """
        :return: 读取cookie
        """
        try:
            cookies = pickle.load(open("damai_cookies.pkl", "rb"))
            for cookie in cookies:
                cookie_dict = {
                    'domain': '.damai.cn',  # 域为大麦网的才为有效cookie
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                }
                self.driver.add_cookie(cookie_dict)
            print('***完成cookie加载***\n')
        except Exception as e:
            print(e)

    def login(self):
        """
        :return: 登录
        """
        if self.login_method == 0:
            self.driver.get(self.config.login_url)
            print('***开始登录***\n')
        elif self.login_method == 1:
            if not os.path.exists('damai_cookies.pkl'):
                # 没有cookie就获取
                self.set_cookie()
            else:
                self.driver.get(self.config.target_url)
                self.get_cookie()

    def enter_concert(self):
        """
        :return: 打开浏览器
        """
        print('***打开浏览器，进入大麦网***\n')
        # 先登录
        self.login()
        # 刷新页面
        self.driver.refresh()
        # 标记登录成功
        self.status = 2
        print('***登录成功***')
        
        # 处理可能的弹窗或遮罩
        try:
            # 检查并关闭可能的弹窗
            popup_selectors = [
                '/html/body/div[2]/div[2]/div/div/div[3]/div[2]',
                "//div[contains(@class, 'modal')]//button[contains(text(), '关闭')]",
                "//div[contains(@class, 'popup')]//span[contains(text(), '×')]"
            ]
            
            for selector in popup_selectors:
                try:
                    popup_element = self.driver.find_element(value=selector, by=By.XPATH)
                    if popup_element.is_displayed():
                        popup_element.click()
                        print("***关闭弹窗***")
                        break
                except:
                    continue
        except Exception as e:
            print(f"弹窗处理异常: {e}")
            
        # 等待页面加载
        time.sleep(2)

    def is_element_exist(self, element):
        """
        :param element: 判断元素是否存在
        :return:
        """
        flag = True
        browser = self.driver
        try:
            browser.find_element(value=element, by=By.XPATH)
            return flag
        except Exception:
            flag = False
            return flag

    def choose_ticket(self):
        """
        :return: 选票
        """
        # 如果登录成功了
        if self.status == 2:
            print("*******************************\n")
            print("***选定城市***\n")
            
            # 检查并处理可能的弹窗
            self.handle_popups()
            
            if self.driver.find_elements(value='citylist', by=By.CLASS_NAME) and self.config.city is not None:
                # 如果可以选择场次，使用新的城市选择器
                city_name_element_list = self.driver.find_element(value='citylist', by=By.CLASS_NAME).find_elements(
                    value='cityitem', by=By.CLASS_NAME)
                for city_name_element in city_name_element_list:
                    if self.config.city in city_name_element.text:
                        city_name_element.click()
                        break
            while self.driver.title.find('订单确认页') == -1:
                try:
                    # 每次循环都检查弹窗
                    self.handle_popups()
                    
                    # 更新购票按钮文本检测，适配新版页面
                    buy_button_text = None
                    buy_link_text = None
                    
                    # 尝试多种按钮选择器
                    buy_button_elements = self.driver.find_elements(value='立即购票', by=By.PARTIAL_LINK_TEXT)
                    if not buy_button_elements:
                        buy_button_elements = self.driver.find_elements(value='立即购买', by=By.PARTIAL_LINK_TEXT)
                    if not buy_button_elements:
                        buy_button_elements = self.driver.find_elements(value='立即预订', by=By.PARTIAL_LINK_TEXT)
                    
                    if buy_button_elements:
                        buy_button_text = buy_button_elements[0].text
                    
                    # 检查其他可能的按钮
                    buy_link_elements = self.driver.find_elements(value='buy-link', by=By.CLASS_NAME)
                    if buy_link_elements:
                        buy_link_text = buy_link_elements[0].text
                    
                    if buy_button_text == "提交缺货登记":
                        # 改变现有状态
                        self.status = 2
                        self.driver.get(self.config.target_url)
                        print('***抢票未开始，刷新等待开始***\n')
                        continue
                    elif buy_button_text in ["立即预订", "立即购票", "立即购买"]:
                        # 选择订单
                        self.choice_order()
                        # 改变现有状态
                        self.status = 3
                    elif buy_button_text == "缺货登记" and self.config.if_listen:
                        # 选择订单
                        self.choice_order()
                        # 改变现有状态
                        self.status = 3
                    elif buy_link_text in ["不，立即预订", "不，立即购买"]:
                        self.driver.find_element(value='buy-link', by=By.CLASS_NAME).click()
                        # 改变现有状态
                        self.status = 3
                    # 选座购买暂时无法完成自动化
                    elif buy_button_text == "选座购买":
                        if buy_button_elements:
                            buy_button_elements[0].click()
                        self.status = 3
                except Exception as e:
                    print(e)
                title = self.driver.title
                if title == '选座购买':
                    # 实现选座购买逻辑
                    self.choice_seat()
                elif title == '订单确认页':
                    while True:
                        # 如果标题为确认订单
                        print('等待...\n')
                        if self.is_element_exist('//*[@id="confirmOrder_1"]'):
                            # 实现确认订单逻辑
                            try:
                                self.commit_order()
                                break
                            except Exception:
                                self.driver.refresh()
                else:
                    print('***抢票未开始，刷新等待开始***\n')
                    time.sleep(1)
                    self.driver.refresh()

    def choice_seat(self):
        while self.driver.title == '选座购买':
            while self.is_element_exist('//*[@id="app"]/div[2]/div[2]/div[1]/div[2]/img'):
                # 座位手动选择 选中座位之后//*[@id="app"]/div[2]/div[2]/div[1]/div[2]/img 就会消失
                print('请快速选择您的座位！！！')
            # 消失之后就会出现 //*[@id="app"]/div[2]/div[2]/div[2]/div
            while self.is_element_exist('//*[@id="app"]/div[2]/div[2]/div[2]/div'):
                # 找到之后进行点击确认选座
                self.driver.find_element(value='//*[@id="app"]/div[2]/div[2]/div[2]/button', by=By.XPATH).click()

    def choice_order(self):
        """
        选择订单：包括场次、票档、人数
        """
        # 检查并处理可能的弹窗
        self.handle_popups()
        
        # 更新购票按钮点击逻辑
        buy_button_elements = self.driver.find_elements(value='立即购票', by=By.PARTIAL_LINK_TEXT)
        if not buy_button_elements:
            buy_button_elements = self.driver.find_elements(value='立即购买', by=By.PARTIAL_LINK_TEXT)
        if not buy_button_elements:
            buy_button_elements = self.driver.find_elements(value='立即预订', by=By.PARTIAL_LINK_TEXT)
        
        if buy_button_elements:
            buy_button_elements[0].click()
            # 点击后再次检查弹窗
            time.sleep(1)
            self.handle_popups()
        
        time.sleep(0.2)
        print("***选定场次***\n")
        
        # 更新场次选择逻辑，使用新的选择器结构
        if self.config.dates:
            try:
                # 查找场次选择区域，使用新的class结构
                date_elements = self.driver.find_elements(value='select_right_list_item', by=By.CLASS_NAME)
                match = False
                for date in self.config.dates:
                    for date_element in date_elements:
                        if date in date_element.text and '无票' not in date_element.text:
                            date_element.click()
                            match = True
                            break
                    if match:
                        break
            except Exception as e:
                print(f"场次选择异常: {e}")
        
        print("***选定票档***\n")
        
        # 更新票档选择逻辑
        if self.config.prices:
            try:
                # 查找票档选择区域，使用新的sku_item类
                price_elements = self.driver.find_elements(value='sku_item', by=By.CLASS_NAME)
                match = False
                for price in self.config.prices:
                    for price_element in price_elements:
                        if price in price_element.text and '缺' not in price_element.text:
                            price_element.click()
                            match = True
                            break
                    if match:
                        break
            except Exception as e:
                print(f"票档选择异常: {e}")
        
        print("***选定人数***\n")
        
        # 更新人数选择逻辑，使用新的加号按钮
        if len(self.config.users) > 1:
            try:
                # 查找加号按钮，使用新的选择器
                plus_buttons = self.driver.find_elements(value='cafe-c-input-number-handler-up', by=By.CLASS_NAME)
                if plus_buttons:
                    for i in range(len(self.config.users) - 1):
                        plus_buttons[0].click()
                        time.sleep(0.1)
                else:
                    # 备用方案：使用原有的JS点击方式
                    for i in range(len(self.config.users) - 1):
                        self.driver.execute_script(
                            'document.getElementsByClassName("number-edit-bg")[1].click();')
            except Exception as e:
                print(f"人数选择异常: {e}")
        
        # 点击确定按钮
        try:
            # 尝试多种确定按钮选择器
            confirm_buttons = self.driver.find_elements(value='确定', by=By.PARTIAL_LINK_TEXT)
            if not confirm_buttons:
                confirm_buttons = self.driver.find_elements(value='立即下单', by=By.PARTIAL_LINK_TEXT)
            if not confirm_buttons:
                confirm_buttons = self.driver.find_elements(value='bui-btn-contained', by=By.CLASS_NAME)
            
            if confirm_buttons:
                confirm_buttons[0].click()
        except Exception as e:
            print(f"确定按钮点击异常: {e}")

    def commit_order(self):
        """
        提交订单
        """
        if self.status in [3]:
            print('***开始确认订单***\n')
            
            # 检查并处理可能的弹窗
            self.handle_popups()
            
            try:
                # 选购票人信息 - 更新观影人选择逻辑
                for user in self.config.users:
                    try:
                        # 方法1：通过用户名定位到选择框
                        xpath_expression = f"//div[text()='{user}']"
                        user_element = self.driver.find_element(value=xpath_expression, by=By.XPATH)
                        
                        # 查找对应的选择图标
                        # 尝试查找未选中的图标
                        unselected_icon = user_element.find_element(value='..',by=By.XPATH).find_element(
                            value='..', by=By.XPATH).find_element(
                            value=".//i[contains(@class, 'icondanxuan-weixuan')]", by=By.XPATH)
                        
                        if unselected_icon:
                            # 如果找到未选中图标，点击选择
                            self.driver.execute_script("arguments[0].click();", unselected_icon)
                            print(f"已选择用户: {user}")
                        
                    except Exception as e1:
                        try:
                            # 方法2：备用选择方案，查找包含用户名的元素
                            user_containers = self.driver.find_elements(value=f"//*[contains(text(), '{user}')]", by=By.XPATH)
                            for container in user_containers:
                                # 在容器附近查找选择图标
                                parent = container.find_element(value='..', by=By.XPATH)
                                icons = parent.find_elements(value=".//i[@class='iconfont']", by=By.XPATH)
                                for icon in icons:
                                    icon_class = icon.get_attribute('class')
                                    if 'icondanxuan-weixuan' in icon_class:
                                        self.driver.execute_script("arguments[0].click();", icon)
                                        print(f"已选择用户: {user} (备用方案)")
                                        break
                                break
                        except Exception as e2:
                            print(f"***购票人信息选中失败: {user}，错误1: {e1}，错误2: {e2}***\n")
                            # 方法3：最后的备用方案，尝试通用选择器
                            try:
                                checkboxes = self.driver.find_elements(value=".//i[contains(@class, 'icondanxuan')]", by=By.XPATH)
                                if checkboxes and len(checkboxes) > len(self.config.users):
                                    # 如果找到足够的复选框，按顺序选择
                                    user_index = self.config.users.index(user)
                                    if user_index < len(checkboxes):
                                        self.driver.execute_script("arguments[0].click();", checkboxes[user_index])
                                        print(f"已选择用户: {user} (通用方案)")
                            except Exception as e3:
                                print(f"***所有购票人选择方案都失败: {user}，最终错误: {e3}***\n")
                
            except Exception as e:
                print("***购票人信息选中失败，请自行查看元素位置***\n")
                print(e)
            
            # 最后一步提交订单
            time.sleep(0.2)
            if self.config.if_commit_order:
                try:
                    # 查找提交订单按钮 - 使用新的选择器
                    submit_buttons = self.driver.find_elements(value='立即提交', by=By.PARTIAL_LINK_TEXT)
                    if not submit_buttons:
                        # 备用方案：使用原有的XPath
                        submit_buttons = self.driver.find_elements(
                            value='//*[@id="dmOrderSubmitBlock_DmOrderSubmitBlock"]/div[2]/div/div[2]/div[2]/div[2]',
                            by=By.XPATH)
                    if not submit_buttons:
                        # 再备用方案：查找包含"提交"文本的按钮
                        submit_buttons = self.driver.find_elements(value="//*[contains(text(), '提交')]", by=By.XPATH)
                    
                    if submit_buttons:
                        submit_buttons[0].click()
                        print("***订单提交成功***\n")
                    else:
                        print("***未找到提交按钮***\n")
                except Exception as e:
                    print(f"***提交订单失败: {e}***\n")

    def finish(self):
        self.driver.quit()
