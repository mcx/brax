# Copyright 2022 The Brax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Trains a robot arm to push a ball to a target."""

from brax.v2 import base
from brax.v2 import math
from brax.v2.base import Transform
from brax.v2.envs import env
from brax.v2.io import mjcf
from etils import epath
import jax
from jax import numpy as jp


class Pusher(env.PipelineEnv):



  # pyformat: disable
  """
  ### Description

  "Pusher" is a multi-jointed robot arm which is very similar to that of a
  human.

  The goal is to move a target cylinder (called *object*) to a goal position
  using the robot's end effector (called *fingertip*). The robot consists of
  shoulder, elbow, forearm, and wrist joints.

  ### Action Space

  The action space is a `Box(-2, 2, (7,), float32)`. An action `(a, b)`
  represents the torques applied at the hinge joints.

  | Num | Action                                        | Control Min | Control Max | Name (in corresponding config) | Joint | Unit         |
  |-----|-----------------------------------------------|-------------|-------------|--------------------------------|-------|--------------|
  | 0   | Rotation of the panning the shoulder          | -1          | 1           | r_shoulder_pan_joint           | hinge | torque (N m) |
  | 1   | Rotation of the shoulder lifting joint        | -1          | 1           | r_shoulder_lift_joint          | hinge | torque (N m) |
  | 2   | Rotation of the shoulder rolling joint        | -1          | 1           | r_upper_arm_roll_joint         | hinge | torque (N m) |
  | 3   | Rotation of hinge joint that flexed the elbow | -1          | 1           | r_elbow_flex_joint             | hinge | torque (N m) |
  | 4   | Rotation of hinge that rolls the forearm      | -1          | 1           | r_forearm_roll_joint           | hinge | torque (N m) |
  | 5   | Rotation of flexing the wrist                 | -1          | 1           | r_wrist_flex_joint             | hinge | torque (N m) |
  | 6   | Rotation of rolling the wrist                 | -1          | 1           | r_wrist_roll_joint             | hinge | torque (N m) |

  ### Observation Space

  Observations consist of

  - Angle of rotational joints on the pusher
  - Angular velocities of rotational joints on the pusher
  - The coordinates of the fingertip of the pusher
  - The coordinates of the object to be moved
  - The coordinates of the goal position

  The observation is a `ndarray` with shape `(23,)` where the elements
  correspond to the table below. An analogy can be drawn to a human arm in order
  to help understand the state space, with the words flex and roll meaning the
  same as human joints.

  | Num | Observation                                              | Min  | Max | Name (in corresponding config) | Joint    | Unit                     |
  |-----|----------------------------------------------------------|------|-----|--------------------------------|----------|--------------------------|
  | 0   | Rotation of the panning the shoulder                     | -Inf | Inf | r_shoulder_pan_joint           | hinge    | angle (rad)              |
  | 1   | Rotation of the shoulder lifting joint                   | -Inf | Inf | r_shoulder_lift_joint          | hinge    | angle (rad)              |
  | 2   | Rotation of the shoulder rolling joint                   | -Inf | Inf | r_upper_arm_roll_joint         | hinge    | angle (rad)              |
  | 3   | Rotation of hinge joint that flexed the elbow            | -Inf | Inf | r_elbow_flex_joint             | hinge    | angle (rad)              |
  | 4   | Rotation of hinge that rolls the forearm                 | -Inf | Inf | r_forearm_roll_joint           | hinge    | angle (rad)              |
  | 5   | Rotation of flexing the wrist                            | -Inf | Inf | r_wrist_flex_joint             | hinge    | angle (rad)              |
  | 6   | Rotation of rolling the wrist                            | -Inf | Inf | r_wrist_roll_joint             | hinge    | angle (rad)              |
  | 7   | Rotational velocity of the panning the shoulder          | -Inf | Inf | r_shoulder_pan_joint           | hinge    | angular velocity (rad/s) |
  | 8   | Rotational velocity of the shoulder lifting joint        | -Inf | Inf | r_shoulder_lift_joint          | hinge    | angular velocity (rad/s) |
  | 9   | Rotational velocity of the shoulder rolling joint        | -Inf | Inf | r_upper_arm_roll_joint         | hinge    | angular velocity (rad/s) |
  | 10  | Rotational velocity of hinge joint that flexed the elbow | -Inf | Inf | r_elbow_flex_joint             | hinge    | angular velocity (rad/s) |
  | 11  | Rotational velocity of hinge that rolls the forearm      | -Inf | Inf | r_forearm_roll_joint           | hinge    | angular velocity (rad/s) |
  | 12  | Rotational velocity of flexing the wrist                 | -Inf | Inf | r_wrist_flex_joint             | hinge    | angular velocity (rad/s) |
  | 13  | Rotational velocity of rolling the wrist                 | -Inf | Inf | r_wrist_roll_joint             | hinge    | angular velocity (rad/s) |
  | 14  | x-coordinate of the fingertip of the pusher              | -Inf | Inf | tips_arm                       | slide    | position (m)             |
  | 15  | y-coordinate of the fingertip of the pusher              | -Inf | Inf | tips_arm                       | slide    | position (m)             |
  | 16  | z-coordinate of the fingertip of the pusher              | -Inf | Inf | tips_arm                       | slide    | position (m)             |
  | 17  | x-coordinate of the object to be moved                   | -Inf | Inf | object (obj_slidex)            | slide    | position (m)             |
  | 18  | y-coordinate of the object to be moved                   | -Inf | Inf | object (obj_slidey)            | slide    | position (m)             |
  | 19  | z-coordinate of the object to be moved                   | -Inf | Inf | object                         | cylinder | position (m)             |
  | 20  | x-coordinate of the goal position of the object          | -Inf | Inf | goal (goal_slidex)             | slide    | position (m)             |
  | 21  | y-coordinate of the goal position of the object          | -Inf | Inf | goal (goal_slidey)             | slide    | position (m)             |
  | 22  | z-coordinate of the goal position of the object          | -Inf | Inf | goal                           | sphere   | position (m)             |


  ### Rewards

  The reward consists of two parts:

  - *reward_near*: This reward is a measure of how far the *fingertip* of the
  pusher (the unattached end) is from the object, with a more negative value
  assigned for when the pusher's *fingertip* is further away from the target.
  It is calculated as the negative vector norm of (position of the fingertip -
  position of target), or *-norm("fingertip" - "target")*.
  - *reward_dist*: This reward is a measure of how far the object is from the
  target goal position, with a more negative value assigned for object is
  further away from the target. It is calculated as the negative vector norm of
  (position of the object - position of goal), or *-norm("object" - "target")*.
  - *reward_control*: A negative reward for penalising the pusher if it takes
  actions that are too large. It is measured as the negative squared Euclidean
  norm of the action, i.e. as *- sum(action<sup>2</sup>)*.

  Unlike other environments, Pusher does not allow you to specify weights for
  the individual reward terms. However, `info` does contain the keys
  *reward_dist* and *reward_ctrl*. Thus, if you'd like to weight the terms, you
  should create a wrapper that computes the weighted reward from `info`.

  ### Starting State

  All pusher (not including object and goal) states start in (0.0, 0.0, 0.0,
  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0). A uniform noise in the
  range [-0.005, 0.005] is added to the velocity attributes only. The velocities
  of the object and goal are permanently set to 0. The object's x-position is
  selected uniformly between [-0.3, 0] while the y-position is selected
  uniformly between [-0.2, 0.2], and this process is repeated until the vector
  norm between the object's (x,y) position and origin is not greater than 0.17.
  The goal always have the same position of (0.45, -0.05, -0.323).

  The default *dt = 0.05*.

  ### Episode Termination

  The episode terminates when any of the following happens:

  1. The episode duration reaches a 1000 timesteps.

  ### Arguments

  No additional arguments are currently supported (in v2 and lower), but
  modifications can be made to the XML file in the assets folder (or by changing
  the path to a modified XML file in another folder)..

  ```
  env = gym.make('Pusher-v2')
  ```

  There is no v3 for Pusher, unlike the robot environments where a v3 and
  beyond take gym.make kwargs such as xml_file, ctrl_cost_weight, reset_noise_scale etc.

  There is a v4 version that uses the mujoco-bindings
  ```
  env = gym.make('Pusher-v4')
  ```

  And a v5 version that uses Brax:

  ```
  env = gym.make('Pusher-v5')
  ```

  ### Version History

  * v5: ported to Brax.
  * v4: all mujoco environments now use the mujoco bindings in mujoco>=2.1.3
  * v2: All continuous control environments now use mujoco_py >= 1.50
  * v1: max_time_steps raised to 1000 for robot based tasks (not including
    reacher, which has a max_time_steps of 50). Added reward_threshold to
    environments.
  * v0: Initial versions release (1.0.0)
  """
  # pyformat: enable


  def __init__(self, backend='generalized', **kwargs):
    if backend == 'positional':
      raise NotImplementedError('Not implemented for positional backend.')
    path = epath.resource_path('brax') / 'v2/envs/assets/pusher.xml'
    sys = mjcf.load(path)

    n_frames = 5

    if backend == 'spring':
      sys = sys.replace(dt=0.001)
      sys = sys.replace(
          actuator=sys.actuator.replace(gear=jp.array([10.0] * sys.act_size()))
      )
      n_frames = 50

    kwargs['n_frames'] = kwargs.get('n_frames', n_frames)

    super().__init__(sys=sys, backend=backend, **kwargs)

    # The tips_arm body gets fused with r_wrist_roll_link, so we use the parent
    # r_wrist_flex_link for tips_arm_idx.
    self._tips_arm_idx = self.sys.link_names.index('r_wrist_flex_link')
    self._object_idx = self.sys.link_names.index('object')
    self._goal_idx = self.sys.link_names.index('goal')

  def reset(self, rng: jp.ndarray) -> env.State:
    qpos = self.sys.init_q

    rng, rng1, rng2 = jax.random.split(rng, 3)

    # randomly orient the object
    cylinder_pos = jp.concatenate([
        jax.random.uniform(rng, (1,), minval=-0.3, maxval=-1e-6),
        jax.random.uniform(rng1, (1,), minval=-0.2, maxval=0.2),
    ])
    # constrain minimum distance of object to goal
    goal_pos = jp.array([0.0, 0.0])
    norm = math.safe_norm(cylinder_pos - goal_pos)
    scale = jp.where(norm < 0.17, 0.17 / norm, 1.0)
    cylinder_pos *= scale
    qpos = qpos.at[-4:].set(jp.concatenate([cylinder_pos, goal_pos]))

    qvel = jax.random.uniform(
        rng2, (self.sys.qd_size(),), minval=-0.005, maxval=0.005
    )
    qvel = qvel.at[-4:].set(0.0)

    pipeline_state = self.pipeline_init(qpos, qvel)

    obs = self._get_obs(pipeline_state)
    reward, done, zero = jp.zeros(3)
    metrics = {'reward_dist': zero, 'reward_ctrl': zero, 'reward_near': zero}
    return env.State(pipeline_state, obs, reward, done, metrics)

  def step(self, state: env.State, action: jp.ndarray) -> env.State:
    x_i = state.pipeline_state.x.vmap().do(
        Transform.create(pos=self.sys.link.inertia.transform.pos)
    )
    vec_1 = x_i.pos[self._object_idx] - x_i.pos[self._tips_arm_idx]
    vec_2 = x_i.pos[self._object_idx] - x_i.pos[self._goal_idx]

    reward_near = -math.safe_norm(vec_1)
    reward_dist = -math.safe_norm(vec_2)
    reward_ctrl = -jp.square(action).sum()
    reward = reward_dist + 0.1 * reward_ctrl + 0.5 * reward_near

    pipeline_state = self.pipeline_step(state.pipeline_state, action)

    obs = self._get_obs(pipeline_state)
    state.metrics.update(
        reward_near=reward_near,
        reward_dist=reward_dist,
        reward_ctrl=reward_ctrl,
    )
    return state.replace(pipeline_state=pipeline_state, obs=obs, reward=reward)

  def _get_obs(self, pipeline_state: base.State) -> jp.ndarray:
    """Observes pusher body position and velocities."""
    x_i = pipeline_state.x.vmap().do(
        Transform.create(pos=self.sys.link.inertia.transform.pos)
    )
    return jp.concatenate([
        pipeline_state.q[:7],
        pipeline_state.qd[:7],
        x_i.pos[self._tips_arm_idx],
        x_i.pos[self._object_idx],
        x_i.pos[self._goal_idx],
    ])