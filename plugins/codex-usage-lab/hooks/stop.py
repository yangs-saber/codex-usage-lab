#!/usr/bin/env python3
"""Official Stop hook: read this transcript only, never resume or call a model."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector import parse, cost


def compact(value):
    if value >= 100000000:
        return f'{value / 100000000:.2f} 亿'
    if value >= 10000:
        return f'{value / 10000:.2f} 万'
    return f'{value:,}'


def report(event):
    if event.get('hook_event_name') != 'Stop':
        return {}
    path, session, turn = (event.get(k) for k in ('transcript_path', 'session_id', 'turn_id'))
    if not all(isinstance(v, str) and v for v in (path, session, turn)):
        return {'systemMessage': '本轮用量暂不可用 · 客户端未提供会话日志或轮次 ID'}
    parsed = parse(Path(path))
    if parsed['id'] != session:
        return {'systemMessage': '本轮用量暂不可用 · 会话日志不匹配'}
    records = {r['key']: r for r in parsed['records']
               if r['thread'] == session and r['turn'] == turn}.values()
    records = list(records)
    if not records:
        return {'systemMessage': '本轮用量暂不可用 · 日志尚无本轮逐次记录'}
    total = cached = inputs = 0
    credits = 0.0
    unknown = assumed = 0
    for record in records:
        usage = record['usage']
        values = [usage.get(k, 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')]
        if any(type(v) is not int or v < 0 for v in values) or values[1] > values[0]:
            return {'systemMessage': '本轮用量暂不可用 · 日志计数异常'}
        total += values[0] + values[2]
        inputs += values[0]
        cached += values[1]
        tier = record['tier']
        assumed += tier is None
        factor = {'default': 1, 'standard': 1, None: 1, 'priority': 2, 'fast': 2, 'ultrafast': 6}.get(tier)
        price = cost(usage, record['model'])
        if tier == 'ultrafast' and record['model'] not in ('gpt-6-astra', 'gpt-6.1-sol'):
            price = None
        if price is None or factor is None:
            unknown += 1
        else:
            credits += price * factor
    parts = [f'本轮 {compact(total)} Token']
    if inputs:
        parts.append(f'缓存 {cached / inputs:.0%}')
    # Partial pricing must never masquerade as the whole turn's cost.
    parts.append('Credits 未完整计价' if unknown else f'估算 {credits:.3f} Credits')
    if assumed and not unknown:
        parts.append('缺失速度按 Standard')
    parts.append('本机日志快照')
    return {'systemMessage': ' · '.join(parts)}


def main():
    try:
        event = json.loads(sys.stdin.read(1048576))
        result = report(event) if isinstance(event, dict) else {}
    except (OSError, ValueError, TypeError, KeyError):
        result = {'systemMessage': '本轮用量暂不可用 · 无法读取本机会话日志'}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
