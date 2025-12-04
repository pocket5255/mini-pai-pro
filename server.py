from mcp.server.fastmcp import FastMCP
from typing import List, Any, Optional
from pathlib import Path
import json
from utils.websocket_manager import WebSocketManager
from msgs.geometry_msgs import Twist
from msgs.sensor_msgs import Image, JointState, Joy
import threading
import time
import logging
import re
from enum import Enum, auto

logger = logging.getLogger('jokes_mcp')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

LOCAL_IP = "127.0.0.1"  # Replace with your local IP address
ROSBRIDGE_IP = "127.0.0.1"  # Replace with your rosbridge server IP address
ROSBRIDGE_PORT = 9091

mcp = FastMCP("ros-mcp-server",host="0.0.0.0")
ws_manager = WebSocketManager(ROSBRIDGE_IP, ROSBRIDGE_PORT, LOCAL_IP)
twist = Twist(ws_manager, topic="/cmd_vel")
image = Image(ws_manager, topic="/camera/image_raw")
jointstate = JointState(ws_manager, topic="/joint_states")
joy = Joy(ws_manager, topic="/joy")

# ----------------------  定义全局变量 ----------------------

class GlobalJoyMode(Enum):
    IDLE = auto()               # 无效模式
    FORWARD = auto()            # 前进
    BACKWARD = auto()           # 后退
    TURN_LEFT = auto()          # 左转
    TURN_RIGHT = auto()         # 右转
    WALK_IN_PLACE = auto()      # 原地踏步

global_joy_thread = None                            # 全局线程变量（初始无线程）
global_delay = 1.5                                  # 全局延迟时间（默认1.5秒）
global_current_mode = GlobalJoyMode.IDLE            # 当前状态

@mcp.tool(description="获取所有 ROS 话题及其类型")
def get_topics():
    topic_info = ws_manager.get_topics()
    ws_manager.close()

    if topic_info:
        topics, types = zip(*topic_info)
        return {
            "topics": list(topics),
            "types": list(types)
        }
    else:
        return "No topics found"

# @mcp.tool(description="发布 Twist 速度消息")
# def pub_twist(linear: List[Any], angular: List[Any]):
#     msg = twist.publish(linear, angular)
#     ws_manager.close()

#     if msg is not None:
#         return "Twist message published successfully"
#     else:
#         return "No message published"

# @mcp.tool(description="按序列发布一组 Twist 速度消息")
# def pub_twist_seq(linear: List[Any], angular: List[Any], duration: List[Any]):
#     twist.publish_sequence(linear, angular, duration)


# @mcp.tool(description="订阅图像消息并下载")
# def sub_image():
#     msg = image.subscribe()
#     ws_manager.close()

#     if msg is not None:
#         return "Image data received and downloaded successfully"
#     else:
#         return "No image data received"

# @mcp.tool(description="发布关节状态 JointState 消息")
# def pub_jointstate(name: list[str], position: list[float], velocity: list[float], effort: list[float]):
#     msg = jointstate.publish(name, position, velocity, effort)
#     ws_manager.close()
#     if msg is not None:
#         return "JointState message published successfully"
#     else:
#         return "No message published"

# @mcp.tool(description="订阅关节状态 JointState 消息")
# def sub_jointstate():
#     msg = jointstate.subscribe()
#     ws_manager.close()
#     if msg is not None:
#         return msg
#     else:
#         return "No JointState data received"

# @mcp.tool(description="发布 Joy 虚拟手柄消息")
# def pub_joy(axes: List[float], buttons: List[int]):
#     msg = joy.publish(axes, buttons)
#     ws_manager.close()
#     if msg is not None:
#         return "Joy message published successfully"
#     else:
#         return "No message published"

@mcp.tool(description="订阅 Joy 虚拟手柄消息")
def sub_joy():
    msg = joy.subscribe()
    ws_manager.close()
    if msg is not None:
        return msg
    else:
        return "No Joy data received"

def release_joy_buttons(delay=0.1):
    def delayed_release():
        time.sleep(delay)
        axes = [0.0]*8
        buttons = [0]*11
        joy.publish(axes, buttons)
        ws_manager.close()
    threading.Thread(target=delayed_release).start()
    
## 自定义函数
## 释放所有按键并停止踏步
def user_release_joy_buttons_and_stop(delay=0.1):
    def delayed_release():
        time.sleep(delay)
        axes = [0.0]*8
        buttons = [0]*11
        buttons[4] = 1  # LB
        joy.publish(axes, buttons)#发布虚拟按键
        ws_manager.close()
        release_joy_buttons() # 释放按键 
        logger.info("机器人 停下")
    threading.Thread(target=delayed_release).start()

# 停止
def user_stop():
    axes = [0.0]*8
    buttons = [0]*11
    buttons[4] = 1  # LB
    joy.publish(axes, buttons)#发布虚拟按键
    ws_manager.close()

# 释放按键
def user_release_joy_buttons():
    # time.sleep(0.1)
    axes = [0.0]*8
    buttons = [0]*11
    joy.publish(axes, buttons)
    ws_manager.close()

# 开始踏步
def user_joy_walk_in_place_start():
    # LB 按下，buttons[4]=1
    axes = [0.0]*8
    buttons = [0]*11
    buttons[4] = 1  # LB
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    # release_joy_buttons()
    
# 停止踏步
def user_joy_walk_in_place_stop():
    # LB 再次按下，buttons[4]=1
    axes = [0.0]*8
    buttons = [0]*11
    buttons[4] = 1  # LB
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    # release_joy_buttons()


@mcp.tool(description="站起来")
def joy_stand_up():
    # 左摇杆按下，axes[9]=1
    axes = [0.0]*8
    buttons = [0]*11
    buttons[9] = 1  # Left Stick Press
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    release_joy_buttons()
    logger.info("机器人 站起来")
    return "Stand up command sent" if msg is not None else "Failed to send stand up command"

@mcp.tool(description="机器人原地踏步，支持秒数参数（最大15秒），例如'原地踏步5秒'或'原地踏步10秒'")
def joy_walk_in_place(duration: str = None):
    """
    让机器人原地踏步指定时间
    
    参数:
        duration: 时间描述，如"5秒"或"10秒"，最大15秒
    """
    # 解析时间参数，默认为5秒
    delay = 5.0  # 默认5秒
    if duration:
        # 使用正则表达式提取数字和单位
        match = re.match(r'(\d+)\s*秒', duration)
        if match:
            value = int(match.group(1))
            # 限制最大值为15秒
            if value > 15:
                value = 15
            delay = float(value)

    global global_delay
    global global_joy_thread
    global global_current_mode
    # 判断线程是否结束
    if global_joy_thread is not None and global_joy_thread.is_alive():
        return "Previous command is still in progress. Please wait."
    else:
        # 向全局变量赋值 并启动线程执行原地踏步动作
        global_delay = delay
        global_current_mode = GlobalJoyMode.WALK_IN_PLACE
        global_joy_thread = threading.Thread(target = user_joy_movement)
        global_joy_thread.start()
        return f"Walk in place {duration} command sent (delay: {delay}s)"

@mcp.tool(description="停下，在收到停止、停下、停止全部动作等命令时执行")
def joy_stop_walk_in_place():
    # LB 再次按下，buttons[4]=1
    axes = [0.0]*8
    buttons = [0]*11
    buttons[4] = 1  # LB
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    release_joy_buttons()
    logger.info("机器人 停下")
    return "Stop walk in place command sent" if msg is not None else "Failed to send stop walk in place command"

# @mcp.tool(description="前进")
# def joy_forward():
#     # 左摇杆上推，axes[1]=1.0
#     axes = [0.0]*8
#     axes[1] = 1.0
#     buttons = [0]*11
#     msg = joy.publish(axes, buttons)
#     ws_manager.close()
#     release_joy_buttons(delay=2)
#     logger.info("机器人 前进")
#     return "Forward command sent" if msg is not None else "Failed to send forward command"


def user_joy_movement():
    """
    统一的线程目标函数，根据global_current_mode判断执行前进、后退、左转、右转或原地踏步动作
    """
    global global_delay
    global global_joy_thread
    global global_current_mode
    
    delay = global_delay
    if delay <= 0:
        delay = 1.5  # 设置默认值，防止无效延迟
    
    # 根据global_current_mode判断执行的动作
    if global_current_mode == GlobalJoyMode.WALK_IN_PLACE:
        # 原地踏步：需要在开始后立即松开按键，否则无法再次触发停止命令
        user_joy_walk_in_place_start()
        time.sleep(0.1)
        user_release_joy_buttons()
        logger.info(f"机器人 原地踏步（{delay}秒）")
        time.sleep(delay)
        # 停止踏步（再次按下 LB），随后松开
        user_joy_walk_in_place_stop()
        time.sleep(0.1)
        user_release_joy_buttons()
    else:
        # 前进、后退、左转、右转：需要开始踏步，然后执行移动动作
        # 开始踏步
        user_joy_walk_in_place_start()
        time.sleep(0.1)
        user_release_joy_buttons()
        
        # 根据global_current_mode判断执行的移动动作
        axes = [0.0]*8
        buttons = [0]*11
        
        if global_current_mode == GlobalJoyMode.FORWARD:
            # 开始前进 # 左摇杆上推，axes[1]=1.0
            axes[1] = 0.8
            logger.info("机器人 前进")
        elif global_current_mode == GlobalJoyMode.BACKWARD:
            # 开始后退 # 左摇杆下推，axes[1]=-1.0
            axes[1] = -0.8
            logger.info("机器人 后退")
        elif global_current_mode == GlobalJoyMode.TURN_LEFT:
            # 开始左转 # 右摇杆左推，axes[3]=1.0
            axes[3] = 0.6
            logger.info("机器人 左转")
        elif global_current_mode == GlobalJoyMode.TURN_RIGHT:
            # 开始右转 # 右摇杆右推，axes[3]=-1.0
            axes[3] = -0.6
            logger.info("机器人 右转")
        
        msg = joy.publish(axes, buttons)
        ws_manager.close()
        time.sleep(delay)
        user_release_joy_buttons()
        time.sleep(0.1)
        # 停止动作
        user_stop()
        time.sleep(0.1)
        user_release_joy_buttons()
    
    # 检查当前线程是否还是全局记录的线程（防止新线程已经覆盖）
    if threading.current_thread() == global_joy_thread:
        global_joy_thread = None
        global_current_mode = GlobalJoyMode.IDLE



@mcp.tool(description="机器人前进，支持步数或米数，例如'前进3步'或'往前走2米'")
def joy_forward(distance: str = None):
    """
    让机器人前进指定距离
    
    参数:
        distance: 距离描述，如"3步"或"2米"
    """
    # 解析距离参数，默认为1步
    delay = 1.5  # 默认3步的时间
    if distance:
        # 使用正则表达式提取数字和单位
        match = re.match(r'(\d+)\s*(步|米)', distance)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            # 根据单位计算延迟时间
            if unit == '步':
                delay = value * 0.5  # 每步0.5秒
            elif unit == '米':
                delay = value * 3     # 每米3秒

    global global_delay
    global global_joy_thread
    global global_current_mode
    # 判断线程是否结束
    if global_joy_thread is not None and global_joy_thread.is_alive():
        return "Previous command is still in progress. Please wait."
    else:
        # 向全局变量赋值 并启动线程执行前进动作
        global_delay = delay
        global_current_mode = GlobalJoyMode.FORWARD
        global_joy_thread = threading.Thread(target = user_joy_movement)
        global_joy_thread.start()
        return f"Forward {distance} command sent (delay: {delay}s)"
        
    #     if 1:
    #         return f"Forward {distance} command sent (delay: {delay}s)"
    #     else:
    #         return "Failed to send forward command"
    # # return f"Forward {distance} command sent (delay: {delay}s)" if msg is not None else "Failed to send forward command"


@mcp.tool(description="机器人后退，支持步数或米数，例如'后退3步'或'往后走2米'")
def joy_backward(distance: str = None):
    """
    让机器人后退指定距离
    
    参数:
        distance: 距离描述，如"3步"或"2米"
    """
    # 解析距离参数，默认为1步
    delay = 1.5  # 默认3步的时间
    if distance:
        # 使用正则表达式提取数字和单位
        match = re.match(r'(\d+)\s*(步|米)', distance)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            # 根据单位计算延迟时间
            if unit == '步':
                delay = value * 0.5  # 每步0.5秒
            elif unit == '米':
                delay = value * 3     # 每米3秒

    global global_delay
    global global_joy_thread
    global global_current_mode
    # 判断线程是否结束
    if global_joy_thread is not None and global_joy_thread.is_alive():
        return "Previous command is still in progress. Please wait."
    else:
        # 向全局变量赋值 并启动线程执行后退动作
        global_delay = delay
        global_current_mode = GlobalJoyMode.BACKWARD
        global_joy_thread = threading.Thread(target = user_joy_movement)
        global_joy_thread.start()
        return f"Backward {distance} command sent (delay: {delay}s)"

@mcp.tool(description="机器人左转，支持角度参数（最大360度），例如'左转90度'或'左转45度'")
def joy_turn_left(angle: str = None):
    """
    让机器人左转指定角度
    
    参数:
        angle: 角度描述，如"90度"或"45度"
    """
    # 解析角度参数，默认为90度
    delay = 3.0  # 默认90度的时间
    if angle:
        # 使用正则表达式提取数字和单位
        match = re.match(r'(\d+)\s*度', angle)
        if match:
            value = int(match.group(1))
            # 根据角度计算延迟时间（90度需要3秒）
            delay = value * (3.0 / 90.0)  # 每度约0.033秒，90度3秒

    global global_delay
    global global_joy_thread
    global global_current_mode
    # 判断线程是否结束
    if global_joy_thread is not None and global_joy_thread.is_alive():
        return "Previous command is still in progress. Please wait."
    else:
        # 向全局变量赋值 并启动线程执行左转动作
        global_delay = delay
        global_current_mode = GlobalJoyMode.TURN_LEFT
        global_joy_thread = threading.Thread(target = user_joy_movement)
        global_joy_thread.start()
        return f"Turn left {angle} command sent (delay: {delay}s)"

@mcp.tool(description="机器人右转，支持角度参数（最大360度），例如'右转90度'或'右转45度'")
def joy_turn_right(angle: str = None):
    """
    让机器人右转指定角度
    
    参数:
        angle: 角度描述，如"90度"或"45度"
    """
    # 解析角度参数，默认为90度
    delay = 3.0  # 默认90度的时间
    if angle:
        # 使用正则表达式提取数字和单位
        match = re.match(r'(\d+)\s*度', angle)
        if match:
            value = int(match.group(1))
            # 根据角度计算延迟时间（90度需要3秒）
            delay = value * (3.0 / 90.0)  # 每度约0.033秒，90度3秒

    global global_delay
    global global_joy_thread
    global global_current_mode
    # 判断线程是否结束
    if global_joy_thread is not None and global_joy_thread.is_alive():
        return "Previous command is still in progress. Please wait."
    else:
        # 向全局变量赋值 并启动线程执行右转动作
        global_delay = delay
        global_current_mode = GlobalJoyMode.TURN_RIGHT
        global_joy_thread = threading.Thread(target = user_joy_movement)
        global_joy_thread.start()
        return f"Turn right {angle} command sent (delay: {delay}s)"

# @mcp.tool(description="机器人坐下")
# def joy_stop():
#     # RB 按下，buttons[5]=1
#     axes = [0.0]*8
#     buttons = [0]*11
#     buttons[5] = 1  # RB
#     msg = joy.publish(axes, buttons)
#     ws_manager.close()
#     release_joy_buttons()
#     return "Stop command sent" if msg is not None else "Failed to send stop command"


@mcp.tool(description="扭腰")
def joy_turn_waist():
    # 右摇杆右推，axes[3]=-1.0
    axes = [0.0]*8
   #axes[2] = -1.0
    axes[5] = -1.0
    buttons = [0]*11
    buttons[0] = 1
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    logger.info("机器人 扭腰")
    return "Turn waist command sent" if msg is not None else "Failed to send turn waist command"

@mcp.tool(description="机器人劈叉、一字马或分腿")
def joy_Split():
    axes = [0.0]*8
    buttons = [0]*11
    axes[5] = -1.0  # RT
    buttons[1] = 1  # B
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    release_joy_buttons(delay=1)
    return "Split command sent" if msg is not None else "Failed to send Split command"

@mcp.tool(description="机器人左右摇摆或平衡")
def joy_balance():
    axes = [0.0]*8
    buttons = [0]*11
    axes[5] = -1.0  # RT
    buttons[2] = 1  # X
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    release_joy_buttons(delay=1)
    return "Maintain balance command sent" if msg is not None else "Failed to send Maintain balance command"

@mcp.tool(description="机器人压腿或拉伸")
def joy_Leg_stretches():
    axes = [0.0]*8
    buttons = [0]*11
    axes[5] = -1.0  # RT
    buttons[3] = 1  # Y
    msg = joy.publish(axes, buttons)
    ws_manager.close()
    release_joy_buttons(delay=1)
    return "Leg stretches command sent" if msg is not None else "Failed to send Leg stretches command"


if __name__ == "__main__":
    mcp.run(transport="stdio")
