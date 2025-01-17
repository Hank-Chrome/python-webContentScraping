import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlparse, urljoin
import threading
import logging
from queue import Queue

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WebsiteDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("网站下载器")

        # URL 输入
        self.url_label = ttk.Label(root, text="网站 URL:")
        self.url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.url_entry = ttk.Entry(root, width=50)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.url_entry.insert(0, "https://harksblog.us.kg")

        # 路径输入
        self.path_label = ttk.Label(root, text="保存路径:")
        self.path_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.path_entry = ttk.Entry(root, width=50)
        self.path_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.path_entry.insert(0, os.path.join(os.getcwd(), "downloads"))
        self.browse_button = ttk.Button(root, text="浏览", command=self.browse_folder)
        self.browse_button.grid(row=1, column=2, padx=5, pady=5)

        # 下载跨域资源选项
        self.download_external = tk.BooleanVar()
        self.download_external_check = ttk.Checkbutton(root, text="下载跨域资源", variable=self.download_external)
        self.download_external_check.grid(row=2, column=0, columnspan=3, pady=5)

        # 开始按钮
        self.start_button = ttk.Button(root, text="开始下载", command=self.start_download)
        self.start_button.grid(row=3, column=0, columnspan=3, pady=10)

        # 进度条
        self.progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.grid(row=4, column=0, columnspan=3, pady=5)

        # 状态标签
        self.status_label = ttk.Label(root, text="")
        self.status_label.grid(row=5, column=0, columnspan=3, pady=5)

        # 调整列的权重，使输入框可以扩展
        root.columnconfigure(1, weight=1)

        # 用于线程安全的队列
        self.queue = Queue()

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder_selected)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        if not self.is_valid_url(url):
            messagebox.showerror("错误", "无效的 URL")
            return

        save_path = self.path_entry.get().strip()
        if not save_path:
            messagebox.showerror("错误", "请填写保存路径")
            return

        # 创建一个新线程来执行下载操作
        threading.Thread(target=self.start_download_thread, args=(url, save_path), daemon=True).start()

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def start_download_thread(self, url, save_path):
        try:
            self.queue.put(("status", "开始下载..."))
            self.download_website(url, save_path)
            self.queue.put(("status", "下载完成！"))
            target_dir = os.path.join(save_path, urlparse(url).netloc.replace(".", "_"))
            self.queue.put(("messagebox", "完成", f"网站下载完成！\n保存路径: {target_dir}"))
        except Exception as e:
            self.queue.put(("status", f"下载失败: {e}"))
            self.queue.put(("messagebox", "错误", f"下载失败: {e}"))
        finally:
            self.queue.put(("progress", 100))

    def download_website(self, url, save_path):
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        website_name = parsed_url.netloc.replace(".", "_")
        target_dir = os.path.join(save_path, website_name)

        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        visited_urls = set()
        urls_to_visit = [url]
        total_urls = 1  # 初始化为1，表示至少有一个URL需要下载

        while urls_to_visit:
            current_url = urls_to_visit.pop(0)
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)

            try:
                response = requests.get(current_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding=response.encoding)

                # 保存网页内容
                file_name = self.get_file_name(current_url, base_url, target_dir)
                file_path = os.path.join(target_dir, file_name)
                try:
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                except Exception as e:
                    logging.error(f"保存 {file_path} 失败: {e}")
                    continue

                # 查找并添加新的链接
                for link in soup.find_all('a', href=True):
                    absolute_link = urljoin(current_url, link['href'])
                    if (absolute_link.startswith(base_url) or self.download_external.get()) and absolute_link not in visited_urls:
                        urls_to_visit.append(absolute_link)
                        total_urls += 1

                # 查找并下载 CSS 文件
                for link in soup.find_all('link', rel='stylesheet', href=True):
                    absolute_link = urljoin(current_url, link['href'])
                    if (absolute_link.startswith(base_url) or self.download_external.get()) and absolute_link not in visited_urls:
                        urls_to_visit.append(absolute_link)
                        total_urls += 1

                # 查找并下载 JavaScript 文件
                for link in soup.find_all('script', src=True):
                    absolute_link = urljoin(current_url, link['src'])
                    if (absolute_link.startswith(base_url) or self.download_external.get()) and absolute_link not in visited_urls:
                        urls_to_visit.append(absolute_link)
                        total_urls += 1

                # 更新进度条
                progress = (len(visited_urls) / total_urls) * 100
                self.queue.put(("progress", progress))
                self.queue.put(("status", f"已下载 {len(visited_urls)} 个页面"))

            except requests.exceptions.RequestException as e:
                logging.error(f"下载 {current_url} 失败: {e}")
                continue

    def get_file_name(self, url, base_url, target_dir):
        path = url.replace(base_url, "", 1).strip()
        if not path:
            return "index.html"
        if path.endswith("/"):
            path = path + "index.html"

        parts = path.split("/")
        if "." not in parts[-1] and not parts[-1].endswith((".html", ".css", ".js")):
            path += ".html"

        # 确保文件名在 Windows 上有效
        invalid_chars = r'[<>:"/\\|?*]'
        path = re.sub(invalid_chars, "_", path)

        return path

    def update_gui(self):
        try:
            while True:
                task = self.queue.get_nowait()
                if task[0] == "status":
                    self.status_label.config(text=task[1])
                elif task[0] == "progress":
                    self.progress_bar['value'] = task[1]
                elif task[0] == "messagebox":
                    messagebox.showinfo(task[1], task[2])
                self.root.update()
        except:
            pass
        self.root.after(100, self.update_gui)

if __name__ == "__main__":
    root = tk.Tk()
    app = WebsiteDownloader(root)
    root.after(100, app.update_gui)
    root.mainloop()