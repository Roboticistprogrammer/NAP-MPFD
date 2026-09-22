from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    infra_profile_arg = DeclareLaunchArgument(
        'd435_infra_profile',
        default_value='640x480x30',
        description='Infra1/Infra2 stream profile (WxHxFPS) -- 640x480x30 verified clean over both USB2 and USB3',
    )
    # Off by default to preserve the original VIO-only bring-up: color adds a
    # third simultaneous stream that OpenVINS doesn't consume.
    enable_color_arg = DeclareLaunchArgument(
        'enable_color',
        default_value='false',
        description='Enable the D435 color stream (unused by OpenVINS; turn on only if a downstream consumer needs it)',
    )

    rs_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [FindPackageShare('realsense2_camera'), '/launch/rs_launch.py']
        ),
        launch_arguments={
            # camera_namespace left empty and camera_name set so topics land flat
            # under /d435i/... (matching dronex_ws's sim bridge naming scheme)
            # rather than the driver's default /camera/camera/... nesting.
            'camera_name': 'd435i',
            'camera_namespace': '',
            'enable_infra1': 'true',
            'enable_infra2': 'true',
            'enable_color': LaunchConfiguration('enable_color'),
            'enable_depth': 'false',
            'depth_module.infra_profile': LaunchConfiguration('d435_infra_profile'),
            'enable_sync': 'true',
        }.items(),
    )

    return LaunchDescription([
        infra_profile_arg,
        enable_color_arg,
        rs_launch,
    ])
