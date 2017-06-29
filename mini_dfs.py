# -*- coding: utf-8 -*-

from const_share import *
from random import choice
import os
import math
import pickle
from enum import Enum
import threading
import sys

operation_names = ('put', 'read', 'fetch', 'quit', 'ls')
OPERATION = Enum('OPERATION', operation_names)

# 全局变量，在Name Node和Data Node之间共享
global_server_block_map = {}
global_read_block = None
global_read_offset = None
global_read_count = None

global_cmd_flag = False
global_file_id = None
global_file_path = None
global_cmd_type = None
global_cmd_type = None

name_event = threading.Event()
ls_event = threading.Event()
read_event = threading.Event()

data_events = []
main_events = []
for j in range(NUM_DATA_SERVER):
    data_events.append(threading.Event())
    main_events.append(threading.Event())


def add_block_2_server(server_id, block, offset, count):
    global global_server_block_map

    if server_id not in global_server_block_map:
        global_server_block_map[server_id] = []
    global_server_block_map[server_id].append((block, offset, count))


def process_cmd(cmd):
    global global_file_path, global_file_id, global_cmd_type
    global global_read_offset, global_read_count

    cmds = cmd.split()
    flag = False
    if len(cmds) >= 1 and cmds[0] in operation_names:
        if cmds[0] == operation_names[0]:
            if len(cmds) != 2:
                print 'Usage: put source_file_path'
            else:
                if not os.path.isfile(cmds[1]):
                    print 'Error: input file does not exist'
                else:
                    global_file_path = cmds[1]
                    global_cmd_type = OPERATION.put
                    flag = True
        elif cmds[0] == operation_names[1]:
            if len(cmds) != 4:
                print 'Usage: read file_id offset count'
            else:
                try:
                    global_file_id = int(cmds[1])
                    global_read_offset = int(cmds[2])
                    global_read_count = int(cmds[3])
                except ValueError:
                    print 'Error: fileid, offset, count should be integer'
                else:
                    global_cmd_type = OPERATION.read
                    flag = True
        elif cmds[0] == operation_names[2]:
            if len(cmds) != 3:
                print 'Usage: fetch file_id save_path'
            else:
                try:
                    global_file_id = int(cmds[1])
                except ValueError:
                    print 'Error: fileid should be integer'
                else:
                    global_cmd_type = OPERATION.fetch
                    flag = True
        elif cmds[0] == operation_names[3]:
            if len(cmds) != 1:
                print 'Usage: quit'
            else:
                flag = True
                global_cmd_type = OPERATION.quit
        elif cmds[0] == operation_names[4]:
            if len(cmds) != 1:
                print 'Usage: ls'
            else:
                flag = True
                global_cmd_type = OPERATION.ls
        else:
            global_cmd_type = OPERATION.quit
            flag = True
    else:
        print 'Usage: put|read|fetch|quit'

    return flag


class NameNode(threading.Thread):

    def __init__(self, name):
        super(NameNode, self).__init__(name=name)
        self.metas = None
        self.id_block_map = None
        self.id_file_map = None
        self.block_server_map = None
        self.last_file_id = -1
        self.last_data_server_id = -1
        self.load_meta()

    def run(self):
        global global_cmd_flag, global_cmd_type

        while True:
            name_event.wait()
            if global_cmd_flag:
                if global_cmd_type == OPERATION.put:
                    self.generate_split()
                elif global_cmd_type == OPERATION.read:
                    self.assign_read_work()
                elif global_cmd_type == OPERATION.fetch:
                    self.assign_fetch_work()
                elif global_cmd_type == OPERATION.ls:
                    self.list_dfs_files()
                else:
                    pass
                name_event.clear()

    def load_meta(self):
        """
        加载Name Node Meta Data
        """
        if not os.path.isfile(NAME_NODE_META_PATH):
            self.metas = {
                'id_block_map': {},
                'id_len_map': {},
                'block_server_map': {},
                'last_file_id': -1,
                'last_data_server_id': -1
            }
        else:
            with open(NAME_NODE_META_PATH, 'rb') as f:
                self.metas = pickle.load(f)
        self.id_block_map = self.metas['id_block_map']
        self.id_file_map = self.metas['id_len_map']
        self.block_server_map = self.metas['block_server_map']
        self.last_file_id = self.metas['last_file_id']
        self.last_data_server_id = self.metas['last_data_server_id']

    def update_meta(self):
        with open(NAME_NODE_META_PATH, 'wb') as f:
            self.metas['last_file_id'] = self.last_file_id
            self.metas['last_data_server_id'] = self.last_data_server_id
            pickle.dump(self.metas, f)

    def list_dfs_files(self):
        print 'total', len(self.id_file_map)
        for file_id, (file_name, file_len) in self.id_file_map.items():
            print LS_PATTERN % (file_id, file_name, file_len)
        ls_event.set()

    def generate_split(self):
        """
        将输入文件划分block，分发到不同的blocks中
        :return:
        """
        global global_server_block_map, global_file_path, global_file_id
        in_path = global_file_path

        file_name = in_path.split('/')[-1]
        self.last_file_id += 1
        server_id = (self.last_data_server_id + 1) % NUM_REPLICATION

        file_length = os.path.getsize(in_path)
        blocks = int(math.ceil(float(file_length) / BLOCK_SIZE))

        # 生成block名字，添加到<id, blocks>映射表中
        self.id_block_map[self.last_file_id] = [BLOCK_PATTERN % (self.last_file_id, i) for i in range(blocks)]
        self.id_file_map[self.last_file_id] = (file_name, file_length)

        for i, block in enumerate(self.id_block_map[self.last_file_id]):
            self.block_server_map[block] = []

            # 备份chunk 3次，分配到不同的DataNode上
            for j in range(NUM_REPLICATION):
                assign_server = (server_id + j) % NUM_DATA_SERVER
                self.block_server_map[block].append(assign_server)

                # 将block和server的分配信息同时添加到全局变量中
                size_in_block = BLOCK_SIZE if i < blocks - 1 else (
                    file_length - BLOCK_SIZE * (blocks - 1))
                add_block_2_server(assign_server, block, BLOCK_SIZE * i, size_in_block)

            server_id = (server_id + NUM_REPLICATION) % NUM_DATA_SERVER

        self.last_data_server_id = (server_id - 1) % NUM_DATA_SERVER
        self.update_meta()

        global_file_id = self.last_file_id
        for data_event in data_events:
            data_event.set()
        return True

    def assign_read_work(self):
        """
        分配读取任务到具体的Data Node上
        :return:
        """
        global global_file_id, global_read_block, global_read_offset, global_read_count
        file_id = global_file_id
        read_offset = global_read_offset
        read_count = global_read_count

        if file_id not in self.id_file_map:
            print 'No such file with id =', file_id
            read_event.set()
        elif (read_offset + read_count) > self.id_file_map[file_id][1]:
            print 'The expected reading exceeds the file, file size:', self.id_file_map[file_id][1]
            read_event.set()
        else:
            start_block = int(math.floor(read_offset / BLOCK_SIZE))
            space_left_in_block = (start_block + 1) * BLOCK_SIZE - read_offset

            if space_left_in_block < read_count:
                print 'Cannot read across blocks'
                read_event.set()
            else:
                # 从存储数据的block中随机选择一个data server，进行数据读取
                read_server_candidates = self.block_server_map[BLOCK_PATTERN % (file_id, start_block)]
                read_server_id = choice(read_server_candidates)
                global_read_block = BLOCK_PATTERN % (file_id, start_block)
                global_read_offset = read_offset - start_block * BLOCK_SIZE
                data_events[read_server_id].set()
                return True

        return False

    def assign_fetch_work(self):
        global global_file_id
        file_id = global_file_id

        if file_id not in self.id_file_map:
            print 'No such file with id =', file_id
        else:
            file_blocks = self.id_block_map[file_id]
            # 获取存储文件的对应server
            return [choice(self.block_server_map[block]) for block in file_blocks]

        return None


class DataNode(threading.Thread):

    def __init__(self, server_id):
        super(DataNode, self).__init__(name='DataServer%s' % (server_id,))
        self._server_id = server_id

    def run(self):
        global global_cmd_flag, global_cmd_type, global_server_block_map

        while True:
            data_events[self._server_id].wait()
            if global_cmd_flag:
                if global_cmd_type == OPERATION.put and self._server_id in global_server_block_map:
                    self.save_file()
                elif global_cmd_type == OPERATION.read:
                    self.read_file()
                else:
                    pass
            data_events[self._server_id].clear()
            main_events[self._server_id].set()

    def save_file(self):
        """
        Data Node根据block的分配情况，进行文件写入
        :return:
        """
        global global_server_block_map, global_file_path

        data_node_dir = DATA_NODE_DIR % (self._server_id,)
        with open(global_file_path, 'r') as f_in:
            for block, offset, count in global_server_block_map[self._server_id]:
                f_in.seek(offset, 0)
                content = f_in.read(count)

                with open(data_node_dir + os.path.sep + block, 'w') as f_out:
                    f_out.write(content)
                    f_out.flush()

    def read_file(self):
        global global_read_block, global_read_offset, global_read_count
        read_path = (DATA_NODE_DIR % (self._server_id,)) + os.path.sep + global_read_block

        with open(read_path, 'r') as f_in:
            f_in.seek(global_read_offset)
            content = f_in.read(global_read_count)
            print content
        read_event.set()


def run():
    name_server = NameNode('NameServer')
    name_server.start()

    data_servers = [DataNode(s_id) for s_id in range(NUM_DATA_SERVER)]
    for server in data_servers:
        server.start()

    global global_cmd_type, global_cmd_flag, global_file_id
    cmd_prompt = 'MiniDFS > '
    print cmd_prompt,
    while True:
        cmd_str = raw_input()
        global_cmd_flag = process_cmd(cmd_str)

        if global_cmd_flag:
            if global_cmd_type == OPERATION.quit:
                sys.exit(0)

            name_event.set()

            if global_cmd_type == OPERATION.put:
                for i in range(NUM_DATA_SERVER):
                    main_events[i].wait()
                print 'Put succeed! File ID is %d' % (global_file_id,)
                global_server_block_map.clear()
                for i in range(NUM_DATA_SERVER):
                    main_events[i].clear()
            elif global_cmd_type == OPERATION.read:
                read_event.wait()
                read_event.clear()
            elif global_cmd_type == OPERATION.ls:
                ls_event.wait()
                ls_event.clear()
            else:
                pass

        print cmd_prompt,


def start_stop_info(operation):
    print operation, 'NameNode'
    for i in range(NUM_DATA_SERVER):
        print operation, 'DataNode' + str(i)

if __name__ == '__main__':
    start_stop_info('Start')
    run()
    start_stop_info('Stop')
    # ns = NameNode('NameServer')
    # ns.list_dfs_files()
