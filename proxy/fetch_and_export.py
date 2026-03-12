#!/usr/bin/env python3
"""
免费代理获取脚本
从公开代理源获取免费代理，测试可用性，并导出为 sub2api 可导入的 JSON 格式

用法:
    python proxy/fetch_and_export.py
    python proxy/fetch_and_export.py --limit 50
    python proxy/fetch_and_export.py --output custom.json
    python proxy/fetch_and_export.py --fetch-proxy 127.0.0.1:7890
"""

import argparse
import json
import sys
import time
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy_list/data/socks5.txt",
]

DEFAULT_TEST_URL = "https://httpbin.org/ip"
DEFAULT_TIMEOUT = 10
DEFAULT_CONCURRENCY = 20


@dataclass
class ProxyInfo:
    raw: str
    protocol: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


def parse_proxy(raw: str) -> Optional[ProxyInfo]:
    raw = raw.strip()
    if not raw:
        return None

    protocol = "http"
    host_port = raw

    if "://" in raw:
        protocol, host_port = raw.split("://", 1)
        protocol = protocol.lower()
    else:
        host_port = raw

    username = None
    password = None
    if "@" in host_port:
        auth, host_port = host_port.split("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)

    if ":" not in host_port:
        return None

    try:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    except ValueError:
        return None

    if not host or port <= 0 or port > 65535:
        return None

    return ProxyInfo(
        raw=raw,
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        password=password,
    )


def fetch_proxies(timeout: int = 30, fetch_proxy: str = "") -> List[str]:
    proxies = set()
    session = requests.Session()
    session.verify = False

    if fetch_proxy:
        p = fetch_proxy if "://" in fetch_proxy else f"http://{fetch_proxy}"
        session.proxies = {"http": p, "https": p}

    print(f"从 {len(PROXY_SOURCES)} 个源获取代理...")
    for url in PROXY_SOURCES:
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        proxies.add(line)
        except Exception as e:
            print(f"  获取失败: {url} - {e}")
            continue

    unique_proxies = sorted(set(proxies))
    print(f"获取到 {len(unique_proxies)} 个原始代理")
    return unique_proxies


def test_proxy(
    proxy: str,
    test_url: str = DEFAULT_TEST_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    proxy_info = parse_proxy(proxy)
    if not proxy_info:
        return {"proxy": proxy, "ok": False, "error": "解析失败"}

    proxy_url = f"{proxy_info.protocol}://{proxy_info.host}:{proxy_info.port}"
    if proxy_info.username and proxy_info.password:
        proxy_url = f"{proxy_info.protocol}://{proxy_info.username}:{proxy_info.password}@{proxy_info.host}:{proxy_info.port}"

    proxies = {"http": proxy_url, "https": proxy_url}

    start = time.time()
    try:
        resp = requests.get(test_url, proxies=proxies, timeout=timeout, verify=False)
        elapsed = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            return {
                "proxy": proxy,
                "ok": True,
                "latency_ms": elapsed,
                "status": resp.status_code,
                "protocol": proxy_info.protocol,
            }
        else:
            return {
                "proxy": proxy,
                "ok": False,
                "latency_ms": elapsed,
                "error": f"HTTP {resp.status_code}",
            }
    except requests.exceptions.Timeout:
        return {"proxy": proxy, "ok": False, "error": "超时"}
    except Exception as e:
        return {"proxy": proxy, "ok": False, "error": str(e)[:50]}


def test_proxies(
    proxies: List[str],
    test_url: str = DEFAULT_TEST_URL,
    timeout: int = DEFAULT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
    limit: int = 100,
) -> List[dict]:
    results = []
    working = []

    print(f"正在测试 {len(proxies)} 个代理 (并发: {concurrency})...")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(test_proxy, p, test_url, timeout): p for p in proxies
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"  进度: {completed}/{len(proxies)}")

            result = future.result()
            results.append(result)

            if result["ok"]:
                working.append(result)

    working.sort(key=lambda x: x.get("latency_ms", 999999))

    print(f"\n测试完成: {len(working)}/{len(proxies)} 可用")

    if limit and len(working) > limit:
        print(f"限制返回前 {limit} 个可用代理")
        working = working[:limit]

    return working


def export_to_sub2api(working_proxies: List[dict], output_path: str) -> str:
    proxies = []

    for idx, p in enumerate(working_proxies):
        proxy_info = parse_proxy(p["proxy"])
        if not proxy_info:
            continue

        item = {
            "name": f"free_proxy_{idx + 1}",
            "protocol": proxy_info.protocol,
            "host": proxy_info.host,
            "port": proxy_info.port,
            "username": proxy_info.username or "",
            "password": proxy_info.password or "",
            "status": "active",
        }

        if not item["username"]:
            del item["username"]
        if not item["password"]:
            del item["password"]

        proxies.append(item)

    output_data = {"proxies": proxies}

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n已导出 {len(proxies)} 个代理到: {output_path}")
    return output_path


def main():
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_output = f"proxies_{timestamp}.json"

    parser = argparse.ArgumentParser(
        description="获取免费代理并导出为 sub2api 导入格式"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="限制可用代理数量 (默认: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=default_output,
        help=f"输出文件路径 (默认: {default_output})",
    )
    parser.add_argument(
        "--test-url",
        type=str,
        default=DEFAULT_TEST_URL,
        help=f"测试 URL (默认: {DEFAULT_TEST_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"测试超时秒数 (默认: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"并发数 (默认: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--fetch-proxy",
        type=str,
        default="",
        help="用于获取代理列表的代理 (国内访问 GitHub 需要)",
    )
    parser.add_argument(
        "--fetch-timeout",
        type=int,
        default=30,
        help="获取代理列表超时秒数 (默认: 30)",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("免费代理获取工具 - sub2api 导出格式")
    print("=" * 50)

    raw_proxies = fetch_proxies(
        timeout=args.fetch_timeout,
        fetch_proxy=args.fetch_proxy,
    )

    if not raw_proxies:
        print("未能获取到任何代理")
        sys.exit(1)

    working = test_proxies(
        raw_proxies,
        test_url=args.test_url,
        timeout=args.timeout,
        concurrency=args.concurrency,
        limit=args.limit,
    )

    if not working:
        print("没有可用的代理")
        sys.exit(1)

    output_path = export_to_sub2api(working, args.output)

    print("\n" + "=" * 50)
    print("导出格式示例:")
    print("=" * 50)
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        print(json.dumps(data, indent=2, ensure_ascii=False)[:800])
        if len(data.get("proxies", [])) > 3:
            print("...")

    print(f"\n完成! 共导出 {len(data.get('proxies', []))} 个可用代理")


if __name__ == "__main__":
    main()
