"""Read creator lists through the existing controlled extension, never submit."""
import re
import time

from .store import Problem, now


def collect_feedback(bridge, expected_account, seconds=180):
    if not expected_account:
        raise Problem('请先在账号设置中确认当前账号')
    deadline = time.monotonic() + seconds
    rows, snapshots = {}, []
    total, full_all, full_published = None, False, False

    def request(action, args=None):
        remaining = deadline - time.monotonic()
        if remaining < 2:
            raise TimeoutError('本轮列表读取已到时间上限')
        return bridge.request(action, args or {}, timeout=min(15, remaining))

    def inspect():
        page = request('creator_inspect')
        if page.get('account', {}).get('user_id') != expected_account:
            raise Problem('后台列表账号与当前设置不一致，未保存观察')
        return page

    def loaded(label):
        for _ in range(6):
            page = inspect()
            cards = page.get('note_cards', [])
            stale = ((label in ('未通过', '审核中') and any(label not in c.get('tags', []) for c in cards)) or
                     (label == '已发布' and any(set(c.get('tags', [])) & {'未通过', '审核中'} for c in cards)))
            if not stale and page.get('url', '').endswith('/new/note-manager') and page.get('list_filter', '').startswith(label):
                return page
            time.sleep(.15)
        raise Problem('笔记状态页尚未完成切换，未把旧列表当成新状态')

    def merge(page, status=None):
        nonlocal total
        if isinstance(page.get('list_total'), int):
            total = page['list_total']
        for card in page.get('note_cards', []):
            note_id = card.get('note_id', '')
            if not re.fullmatch(r'[a-f0-9]{24}', note_id):
                raise Problem('后台列表缺少可靠笔记ID，未保存观察')
            tags = card.get('tags', [])
            metrics = card.get('metrics', [])
            row = rows.setdefault(note_id, {'_id': note_id, '审核状态': '未取得', '可见范围': '未取得'})
            row.update({'标题': card.get('title', ''), '发布时间': card.get('time', ''),
                        '列表标签': tags, '标题为列表文本': True})
            for i, name in enumerate(['观看', '评论', '点赞', '收藏', '分享']):
                row[name] = metrics[i] if i < len(metrics) else None
            if status:
                row['审核状态'] = status
            if '未通过' in tags:
                row['审核状态'] = '未通过'
            elif '审核中' in tags:
                row['审核状态'] = '审核中'
            if '仅自己可见' in card.get('text', ''):
                row['可见范围'] = '仅自己可见'
            # Absence of a private badge never proves public visibility.
        snapshots.append({'filter': page.get('list_filter'), 'loaded': len(page.get('note_cards', [])),
                          'observed_at': page.get('observed_at')})

    def scan(page, status=None, expected=None):
        seen, stable = set(), 0
        for _ in range(12):
            merge(page, status)
            current = {c['note_id'] for c in page.get('note_cards', [])}
            stable = stable + 1 if current == seen else 0
            seen |= current
            if expected is not None and len(seen) >= expected:
                return True
            if stable >= 2:
                return False
            request('scroll', {'direction': 'down'})
            page = loaded('已发布' if status == '已发布' else '全部')
        return False

    start = inspect()
    if start.get('editor_has_content'):
        raise Problem('当前编辑器有内容；请先保存草稿再回收后台数据')
    if start.get('drafts') or any(n.get('target') == 'draft_close' for n in start.get('navigation', [])):
        request('creator_navigate', {'target': 'draft_close'})
    request('creator_navigate', {'target': 'notes'})
    request('creator_navigate', {'target': 'all'})
    partial = ''
    try:
        page = loaded('全部')
        full_all = scan(page, expected=page.get('list_total'))
        request('creator_navigate', {'target': 'rejected'})
        page = loaded('未通过')
        merge(page, '未通过')
        request('creator_navigate', {'target': 'reviewing'})
        page = loaded('审核中')
        merge(page, '审核中')
        published_count = sum(r['审核状态'] in ('审核中', '未通过') for r in rows.values())
        request('creator_navigate', {'target': 'published'})
        page = loaded('已发布')
        full_published = scan(page, '已发布', max(0, total - published_count) if total is not None else None)
        request('creator_navigate', {'target': 'all'})
        loaded('全部')
    except TimeoutError as error:
        partial = str(error)
    complete = full_all and full_published and not partial and len(rows) == total and all(r['审核状态'] != '未取得' for r in rows.values())
    if not complete and not partial:
        partial = f'滚动后平台未返回完整列表或审核状态；本轮取得{len(rows)}篇，平台全部计数为{total}'
    return {'account': start['account'], 'observed_at': now(), 'rows': list(rows.values()),
            'total': total, 'complete': complete, 'list_snapshots': snapshots,
            'coverage': ('当前账号列表全量核对' if complete else '本轮已加载列表，非全量') +
                        '；浏览/赞/收藏/评论/分享快照，不包含曝光；无私密标签不等于公开',
            'partial_reason': partial, 'published_by_this_action': False}
