# -*- coding: utf-8 -*-


"""
文件名称： dfs_util.py
功能描述： mini-dfs基本数据结构
创建者： zhaoyang.liu, weiyu.chen
创建日期： 2017年06月21日
修改日期          修改人          修改内容
"""


class FileRange:

    def __init__(self, offset, count, block_id):
        self._offset = offset
        self._count = count
        self._block_id = block_id


class TreeNode:

    def __init__(self, value, is_file):
        self._value = value
        self._is_file = is_file
        self._parent = None
        self._first_child = None
        self._next_sibling = None

    def find_node(self, path, is_file, node_parent):
        pass


class FileTree:

    def __init__(self):
        self._root = TreeNode('/', False)



