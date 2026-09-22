from setuptools import find_packages, setup

package_name = 'dronex_px4_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dronex',
    maintainer_email='amirsalar1379@yahoo.com',
    description='Bridges OpenVINS VIO output and PX4 IMU over px4_msgs (uXRCE-DDS)',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'vio_px4_bridge = dronex_px4_bridge.vio_px4_bridge_node:main',
        ],
    },
)
