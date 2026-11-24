import copy
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills'/'trace-diagram'/'scripts'))
from route_graph import Graph
from trace import Overlay, prefix


def sample(name):
    folder = ROOT/'examples'/name
    data = json.loads((folder/'route.json').read_text(encoding='utf-8'))
    with Image.open(folder/'source.png') as im:
        return data, im.convert('RGB')


class DiagramTests(unittest.TestCase):
    def test_sample_routes_against_business_outcomes(self):
        expected = {
            'crossed-lines': {'order_next': ['接收订单','校验库存']},
            'sample-intake': {'intake': ['样品签收','登记批次','放入样柜']},
            'unit-check': {'consistent': ['提交数据','单位一致？','确认入库'],
                           'inconsistent': ['提交数据','单位一致？','标记待核']},
            'resubmission': {'resubmit_once': ['提交材料','受理','材料齐全？','补充材料','提交材料','受理','材料齐全？','归档']}
        }
        for name, scenes in expected.items():
            data, image = sample(name)
            graph = Graph(data, image.size)
            for sid, labels in scenes.items():
                with self.subTest(name=name, scene=sid):
                    route = graph.walk(sid)
                    nodes = [route[0]['from'], *[edge['to'] for edge in route]]
                    self.assertEqual([graph.nodes[n]['label'] for n in nodes], labels)

    def test_uncertain_edge_can_be_reviewed_and_blocks_only_affected_scene(self):
        data, image = sample('unit-check')
        data['edges'][-1].update(to=None, uncertain='arrowhead hidden')
        graph = Graph(data, image.size)
        self.assertGreater(Overlay(image,graph,None).graph_review(graph,'inconsistent').height, image.height)
        self.assertEqual(len(graph.walk('consistent')),2)
        with self.assertRaisesRegex(ValueError,'E3.*arrowhead hidden'):
            graph.walk('inconsistent')

    def test_crossing_and_unoriented_link(self):
        data, image = sample('crossed-lines')
        graph = Graph(data,image.size)
        self.assertEqual(len(graph.nodes),4)
        self.assertEqual(graph.edges['E2']['to'],'N3')
        self.assertTrue(graph.edges['E3']['uncertain'])
        # No arrowhead should appear on either end of an unoriented link.
        review = Overlay(image,graph,None).graph_review(graph,'order_next')
        for pt in [(841,386),(845,386)]:
            self.assertEqual(review.getpixel(pt),image.getpixel(pt))
        data['scenes'][0]['edges'].append('E3')
        with self.assertRaisesRegex(ValueError,'E3'):
            Graph(data,image.size).walk('order_next')

    def test_disconnected_route(self):
        data, image = sample('resubmission')
        data['scenes'][0]['edges'].pop(1)
        graph = Graph(data, image.size)
        with self.assertRaisesRegex(ValueError,'expected'):
            graph.walk('resubmit_once')

    def test_reversed_geometry(self):
        data, image = sample('resubmission')
        data['edges'][0]['points'].reverse()
        with self.assertRaisesRegex(ValueError,'E1.*misses'):
            Graph(data,image.size)

    def test_duplicate_id_and_mismatched_image(self):
        data, image = sample('resubmission')
        with self.assertRaisesRegex(ValueError,'size'):
            Graph(data,(1,1))
        changed = copy.deepcopy(data)
        changed['nodes'].append(data['nodes'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            Graph(changed,image.size)

    def test_route_traverses_bend_at_arclength(self):
        points = [(0,0),(0,30),(70,30)]
        self.assertEqual(prefix(points,.5),[(0,0),(0,30),(20,30)])
        self.assertEqual(prefix(points,1),points)


if __name__ == '__main__':
    unittest.main()
