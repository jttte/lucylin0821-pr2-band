#!/usr/bin/env python

"""This module implements some baseline behaviors for the sushi tasks. If you
want to experiment with other ideas there are a few intended places to do so.
If you want to replace the perception, write a new file which exposes the same
interface as perception.py and change the import in this file.
If you want to replace the high level behavior functions, you should probably
write your own versions of functions like clean_table_simple().
If you really want to overhaul the whole thing, write your own behavior program
to replace main.py. Of course reuse whatever bits you can.

"""

from math import atan2, pi, sqrt
import sys
from time import sleep
from os import system
import roslib; roslib.load_manifest('sushi')

from geometry_msgs.msg import (Point, PointStamped, Point32, Pose, PoseStamped,
                               PoseWithCovariance, PoseWithCovarianceStamped,
                               Quaternion, Vector3)
import rospy
from rospy import logerr, loginfo, Time
from sensor_msgs.msg import ChannelFloat32, PointCloud
from std_msgs.msg import Header, ColorRGBA

from util.simplecontrollers import base, head, speech
from carrier import pregrasp, grasp, lift, pick_up, put_down
# When ready for swapable perception, add command line arg to choose which to
# load.
import hardcodedperception as perception
import poop_scoop.srv
from subscription_buffer import SubscriptionBuffer


# These are radiuses from the robot's position:
WORK_DIST = 0.4
MAX_WORK_DIST = 0.8


#def go_to_scoop_poop_at(base, poop_x_map, poop_y_map, offset):
#    base_x = base.get_x_map()
#    base_y = base.get_y_map()
#    x, y, yaw = calc_work_x_y_yaw(base_x, base_y, poop_x_map, poop_y_map, offset)
#    rospy.logerr("Calling move base.")
#    return base.go_to(x, y, yaw)


#def scoop_poops_and_go_back(base, scooper, poops):
#    """poops is a list of tuples (map_x, map_y)."""
#    for poop in poops:
#      if go_to_scoop_poop_at(base, poop[0], poop[1],0):
#          scooper.scoop()
##    base.go_to_start()


# Distance from the dirty table that the robot should try to get to drop off
# objects.
DIRTY_TABLE_WORK_DIST = 0.5

# To start with, we won't try to find free space on the dirty table to put
# object onto. We'll just hold the obj DIRTY_DROP_HEIGHT over the middle of the
# dirty table and let go.
DIRTY_DROP_HEIGHT = 0.1


def clean_table_v1():
    """Open loop. Assumes dirty objects are reachable from 1 pose. Hard codes
    poses.
    
    """
    pick_up_pose = MapPose() # TODO hardcode it
    drop_off_pose = MapPose() # TODO hardcode it
    objs = perception.objs_on_surface(eating_table_corners)
    for obj in objs:
        base.go_to_pose(pick_up_pose)
        carrier.pick_up(obj, carrier.LEFT_HAND)
        base.go_to_pose(drop_off_pose)
        loginfo("For now, dropping stuff above the dirty table.")
        wrist_drop_pose = carrier.wrist_pose(carrier.LEFT_HAND)
        wrist_drop_pose.x = MapInt(10)
        wrist_drop_pose.y = MapInt(5)
        wrist_drop_pose.z = MapInt(7)
        carrier.wrist_to(wrist_drop_pose)
        carrier.open_gripper(carrier.LEFT_HAND)
    loginfo("Done clearing the eating table.")

    
def clean_table_v2():
    """Simple cleanup algorithm which makes various assumptions and brings
    items 1 at a time to the dirty table.

    """
    # This assumes that perception will be smart enough to remember the most
    # accurate info it's seen. If it's not, this should be modified to only
    # call perception when near the target.
    clean_table_corners, objs = prepare_to_clean_table()
    while len(objs) > 0:
        objs = perception.objs_on_surface(eating_table_corners)
        closest_obj = find_closest_obj(objs)
        get_within_working_dist(closest_obj)
        carrier.pick_up(closest_obj, carrier.LEFT_HAND)
        go_to_dirty_table()
        loginfo("For now, dropping stuff above the dirty table.")
        drop_position = MapPosition(dirty_table_center.x, dirty_table_center.y,
                                    dirty_table_center.z + DIRTY_DROP_HEIGHT)
        carrier.put_down_obj_at(drop_position, carrier.LEFT_HAND)
    loginfo("Done clearing the eating table.")


def prepare_to_clean_table():
    """Moves the robot to the eating table and returns the table corners and a
    list of objects on the table.
    
    """
    eating_table_corners = perception.eating_table_corners()
    loginfo("Found eating table with corners " + eating_table_corners)
    examine_pose = plan_examine_surface(base.get_pose(), eating_table_corners)
    loginfo("Moving to %s to examine the eating table better." % base_pose)
    base.go_to_pose(examine_pose)
    eating_table_corners = perception.eating_table_corners()
    loginfo("Reexamined eating table. Found corners: " + eating_table_corners)
    objs = perception.objs_on_surface(eating_table_corners)
    loginfo("Found dirty objects on table: " + objs)
    return table_corners, objs


def find_closest_obj(objs):
    if len(objs) == 0:
        raise ValueError("Can't find closest obj without any objs")
    objs_with_dists = []
    for obj in objs:
        dist = dist_between(obj.pose, base.get_pose())
        objs_with_dists.append((obj, dist))
    def get_dist(obj_with_dist):
        return obj_with_dist[1]
    objs_with_dists.sort(key=get_dist)
    loginfo("Objects and their distances: " + objs_with_dists)
    return objs_with_dists[0]


def get_within_working_dist(pos):
    """Takes a position or pose."""
    if dist_between(base.get_pose(), pos) <= MAX_WORK_DIST:
        loginfo("Already within working dist of: " + obj)
        return
    desired_pose = calc_work_pose(base.get_pose(), pos, WORK_DIST)
    dest_pose = find_nearest_valid_pose(desired_pose)
    loginfo("Moving to within working dist of: " + pose)
    base.go_to_pose(dest_pose)


def go_to_dirty_table():
    dirty_table_center = perception.dirty_table_center()
    loginfo("Found dirty table with center " + dirty_table_center)
    get_within_working_dist(dirty_table_center)

    
def find_nearest_valid_pose(pose):
    # TODO Sachin
    return pose


def main():
    loginfo("Poop Scoop logic starting up.")
    rospy.init_node('sushi_main')
    sleep(1) # Wait for simple controller to come up
    head.look_down()
   
    mode = sys.argv[1]
    
    # Base motion modes
    if mode == 'reset_pose':
        base.reset_pose()
    elif mode == 'go_to_start':
        base.go_to_start()
    elif mode == 'go_to':
        x_map = float(sys.argv[2])
        y_map = float(sys.argv[3])
        yaw_map = pi / 2
        if len(sys.argv) >= 5:
            yaw_map = float(sys.argv[4])
        base.go_to(x_map, y_map, yaw_map)
    
    # Parts of behaviors for testing
    elif mode == 'look_down':
        head.look_down()
    elif mode == 'look_up':
        head.look_up()
    elif mode == 'talk':
        speak("Clean up, clean up, everybody everywhere.")
    elif mode == 'get_within_working_dist':
        obj = parse_obj_args(sys.argv[2:])
        get_within_working_dist(obj.pose)
    elif mode == 'pregrasp':
        obj = parse_obj_args(sys.argv[2:])
        carrier.pregrasp(obj, LEFT_HAND)
    elif mode == 'grasp':
        obj = parse_obj_args(sys.argv[2:])
        carrier.grasp(obj, LEFT_HAND)
    elif mode == 'lift':
        obj = parse_obj_args(sys.argv[2:])
        carrier.lift(obj, LEFT_HAND)
    elif mode == 'pick_up':
        obj = parse_obj_args(sys.argv[2:])
        carrier.pick_up(obj, LEFT_HAND)
    elif mode == 'go_and_pick_up':
        obj = parse_obj_args(sys.argv[2:])
        get_within_working_dist(obj.pose)
        carrier.pick_up(obj, LEFT_HAND)
    elif mode == 'go_and_put_down':
        obj_id = int(sys.argv[2])
        x, y, z = [float(x) for x in sys.argv[3:6]]
        obj_type = objdb.by_id(obj_id).type
        dummy_pose = MapPose(0, 0, 0, 0, 0, 0)
        obj = Obj(obj_type, dummy_pose)
        dest = MapPosition(x, y, z)
        carrier.put_down(obj, dest, LEFT_HAND)
    elif mode == 'drag_plate_to_edge':
        obj = parse_obj_args(sys.argv[2:])
        drag_plate_to_edge(obj, LEFT_HAND)
    
    # Full task modes
    elif mode == 'clean_table_v1':
        clean_table_v1()
        base.go_to_start()
#    elif mode == 'v1':
#        POOP = (6.065, 1.9)
#        go_to_scoop_poop_at(base, POOP[0], POOP[1],0)
#        scooper.scoop()
#        base.go_to_start()
#    elif mode == 'v2':
#        hall1_poops = [
#            (6.065, 1.9),
#            (5.644, 3.173),
#            (6.620, 4.657),
#        ]
#        scoop_poops_and_go_back(base, scooper, hall1_poops)
#    elif mode == 'v3':
#        hall2_poops = [
#            (1.357, -0.157),
##            (23.2, 60.06),
#        ]
#        poop_perception = SubscriptionBuffer('/poo_view', PointCloud,
#                                             blocking=True)
#        points = poop_perception.get_last().points
#        poops = [(p.x, p.y) for p in points if p.z != 25]
#        poops = hall2_poops
#        loginfo("Got the following FAKE poops: %s" % poops)
#        
#        base_x = base.get_x_map()
#        base_y = base.get_y_map()
#        poops_w_dist = [(p[0], p[1], dist_between(p[0], p[1], base_x, base_y))
#                        for p in poops]
#        def get_dist(poop_w_dist):
#            return poop_w_dist[2]
#        poops_w_dist.sort(key=get_dist)
#        loginfo("Poops (map x, map y, distance) sorted by distance: %s" %
#                poops_w_dist)
#        
#        scoop_poops_and_go_back(base, scooper, poops_w_dist)
#    elif mode == 'v4':
#        poop_perception = SubscriptionBuffer('/poo_view', PointCloud,
#                                             blocking=True)
#
#        speak("Hello! Its time for me to scoop some poop.")
#
#        while not rospy.is_shutdown():
#            if base._moving:
#              loginfo("\nMOVING\n")
#              sleep(1.0)
#              continue
#
#            visualize_base_ray()
#       
#            logerr("\n\n[stage 1] Getting new list of poops.")
#            points = poop_perception.get_last().points
#            poops = [(p.x, p.y) for p in points if p.z != 25]
#            #loginfo("Got the following real poops: %s" % poops)
#            if len(poops) == 0:
#              loginfo("[stage 1] No poops found.")
#              break
#            
#            base_x = base.get_x_map()
#            base_y = base.get_y_map()
#            poops_w_dist = [(p[0], p[1],
#                             dist_between(p[0], p[1], base_x, base_y))
#                            for p in poops]
#            def get_dist(poop_w_dist):
#                return poop_w_dist[2]
#            poops_w_dist.sort(key=get_dist)
#            #loginfo("Poops (map x, map y, distance) sorted by distance: %s" %
#            #        poops_w_dist)
#            closest = poops_w_dist[0]
#            if closest[2] > 1.5:
#              loginfo("[stage 1] Closest poop is too far.");
#              continue
#        
#            visualize_poop(closest[0],closest[1],0.02,0,"/map","sensed_poop")
#            x, y, yaw = calc_work_x_y_yaw(base_x, base_y, closest[0],closest[1],STAGE1_OFFSET)
#            visualize_poop(x,y,0.02,3,"/map","projected_scoop")
#
#                        
#            #if is_in_bounds(closest[0], closest[1]):
#            if not point_inside_polygon(closest[0], closest[1]):
#              #speak("Out of bounds.")
#              loginfo("[stage 1] Poop location is out of bounds. Ignoring.")
#              continue
#
#
#            logerr("[stage 1] Sending poop to move_base.")
#            if go_to_scoop_poop_at(base, closest[0], closest[1], STAGE1_OFFSET):
#              visualize_base_ray()
#              head.look_down() 
#              sleep(0.5)
#              while base._moving:
#                loginfo("\n[stage 2] Ignoring perception while I'm moving.\n")
#                sleep(1.0)
#              sleep(2.0);
#              lost_goal_poop = True
#              start_resense = rospy.get_time()
#              resense_failed = False   # a timeout for resensing
#              while lost_goal_poop:
#                if rospy.get_time()-start_resense >= RESENSE_TIMEOUT:
#                  logerr("[stage 2] TIMED OUT (%0.3f sec).", rospy.get_time()-start_resense)
#                  resense_failed = True
#                  break
#
#                logerr("[stage 2] Getting new list of poops.")
#                points = poop_perception.get_last().points
#                poops = [(p.x, p.y) for p in points if p.z != 25]
#                #loginfo("Got the following real poops: %s" % poops)
#                if len(poops) == 0:
#                  continue
#            
#                base_x = base.get_x_map()
#                base_y = base.get_y_map()
#                poops_w_dist = [(p[0], p[1],
#                             dist_between(p[0], p[1], closest[0], closest[1]))
#                            for p in poops]
#                def get_dist(poop_w_dist):
#                  return poop_w_dist[2]
#                poops_w_dist.sort(key=get_dist)
#                #loginfo("Poops (map x, map y, distance) sorted by distance: %s" %
#                #        poops_w_dist)
#                closest2 = poops_w_dist[0]
#                visualize_poop(closest2[0],closest2[1],0.02,1,"/map","resensed_poop") 
#
#                x, y, yaw = calc_work_x_y_yaw(base_x, base_y, closest2[0],closest2[1],0)
#                visualize_poop(x,y,0.02,2,"/map","reprojected_scoop")
#
#                if closest2[2] > 0.5:
#                  loginfo("[stage 2] Resensed poop is too far from sensed poop.  dist:%f.", closest2[2]);
#                  sleep(2)
#                else:
#                  lost_goal_poop = False
#
#              if not resense_failed:
#                go_to_scoop_poop_at(base, closest2[0], closest2[1], 0)
#                visualize_base_ray()
#                speak("Scooping")
#                sleep(0.5);
#
#
#                # entering stage 3 #
##                logerr("\n\n [stage 3] Getting poops.")
##                points = poop_perception.get_last().points
##                poops = [(p.x, p.y) for p in points if p.z != 25]
##                if len(poops) == 0:
##                    break
#            
##                base_x = base.get_x_map()
##                base_y = base.get_y_map()
##                poops_w_dist = [(p[0], p[1],
##                                 dist_between(p[0], p[1], base_x, base_y))
##                                for p in poops]
##                def get_dist(poop_w_dist):
##                    return poop_w_dist[2]
##                poops_w_dist.sort(key=get_dist)
##                closest = poops_w_dist[0]
##                if closest3[2] > 0.10:
##                    loginfo("[stage 3] Closest poop is further than 10cm away.");
##                    continue 
##                x, y, yaw = calc_work_x_y_yaw(base_x, base_y, closest3[0],closest3[1])
##                visualize_poop(x,y,0.02,2,"/map","reprojected_scoop")
# 
#                loginfo("[resense] Reached goal. Starting scoop.");
#                scooper.scoop()
#                head.look_down()
#            else:
#              speak("Can't find the poop anymore.")
#              logerr("Planning to poop failed.")
#            sleep(5)
#            #head.look_up()
#            #sleep(10)


def parse_obj_args(obj_command_line_args):
    # All pose data is in the map frame
    obj_id = int(obj_command_line_args[0])
    obj_type = objdb.by_id(obj_id).type
    obj_pose = [float(x) for x in obj_command_line_args[1:7]]
    return Obj(obj_type, obj_pose)


if __name__ == '__main__':
    try:
        main()
    except rospy.ROSInterruptException:
        pass
