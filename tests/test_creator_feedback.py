import unittest

from xhs_operator.creator import collect_feedback
from xhs_operator.store import Problem

ACCOUNT = 'a' * 24


class CreatorBridge:
    def __init__(self, *, account=ACCOUNT, dirty=False, total=3, invalid=False):
        self.account, self.dirty, self.total, self.invalid = account, dirty, total, invalid
        self.filter, self.scrolled, self.actions = '全部', False, []

    def request(self, action, args=None, **_):
        self.actions.append((action, args))
        if action == 'creator_navigate':
            self.filter = {'notes': '全部', 'all': '全部', 'published': '已发布',
                           'reviewing': '审核中', 'rejected': '未通过'}[args['target']]
            self.scrolled = False
            return {}
        if action == 'scroll':
            self.scrolled = True
            return {}
        def card(n, tags):
            return {'note_id': str(n) * 24, 'title': '同名标题', 'time': '2026-10-24',
                    'tags': tags, 'text': '\n'.join(tags), 'metrics': ['48', '2', '4', '5', '1']}
        cards = [card(1, []), card(2, ['仅自己可见']), card(3, ['未通过'])]
        if self.invalid:
            cards[0]['note_id'] = 'no-id'
        if self.filter == '已发布':
            cards = cards[:2]
        elif self.filter == '未通过':
            cards = cards[2:]
        elif self.filter == '审核中':
            cards = []
        elif not self.scrolled:
            cards = cards[:1]
        return {'account': {'user_id': self.account}, 'url': 'https://creator.xiaohongshu.com/new/note-manager',
                'editor_has_content': self.dirty, 'list_filter': self.filter, 'list_total': self.total,
                'observed_at': '2026-10-24T01:00:00+08:00', 'note_cards': cards}


class CreatorFeedbackTests(unittest.TestCase):
    def test_collects_distinct_ids_and_review_states_without_claiming_public_or_impressions(self):
        bridge = CreatorBridge()
        result = collect_feedback(bridge, ACCOUNT)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['rows']), 3)
        rows = {r['_id']: r for r in result['rows']}
        self.assertEqual(rows['1' * 24]['审核状态'], '已发布')
        self.assertEqual(rows['1' * 24]['可见范围'], '未取得')
        self.assertEqual(rows['2' * 24]['可见范围'], '仅自己可见')
        self.assertEqual(rows['3' * 24]['审核状态'], '未通过')
        self.assertNotIn('曝光', rows['1' * 24])
        self.assertFalse(result['published_by_this_action'])
        self.assertEqual(bridge.filter, '全部')

    def test_wrong_account_and_unsaved_editor_stop_before_navigation(self):
        for bridge in [CreatorBridge(account='b' * 24), CreatorBridge(dirty=True)]:
            with self.assertRaises(Problem):
                collect_feedback(bridge, ACCOUNT)
            self.assertEqual(len(bridge.actions), 1)

    def test_missing_note_id_is_not_saved_or_replaced_with_title(self):
        with self.assertRaisesRegex(Problem, '笔记ID'):
            collect_feedback(CreatorBridge(invalid=True), ACCOUNT)

    def test_stalled_list_is_reported_as_partial_instead_of_account_coverage(self):
        result = collect_feedback(CreatorBridge(total=8), ACCOUNT)
        self.assertFalse(result['complete'])
        self.assertIn('非全量', result['coverage'])

    def test_filter_switch_does_not_relabel_the_previous_list_as_reviewing(self):
        class StaleBridge(CreatorBridge):
            pending = True
            def request(self, action, args=None, **kw):
                if action == 'creator_inspect' and self.filter == '审核中' and self.pending:
                    self.pending = False
                    self.filter = '已发布'
                    result = super().request(action, args, **kw)
                    self.filter = '审核中'
                    result['list_filter'] = '审核中'
                    return result
                return super().request(action, args, **kw)
        result = collect_feedback(StaleBridge(), ACCOUNT)
        self.assertTrue(result['complete'])
        self.assertEqual(sum(r['审核状态'] == '审核中' for r in result['rows']), 0)
