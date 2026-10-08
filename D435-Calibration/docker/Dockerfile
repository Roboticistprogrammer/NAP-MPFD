# Kalibr (ROS1 Noetic) for arm64 / amd64 -- adapted from ethz-asl/kalibr Dockerfile_ros1_20_04.
# Ubuntu 24.04 has no ROS1, so Kalibr lives in this container; bags are converted ROS2 -> ROS1 on the host.
FROM ros:noetic-ros-base

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget autoconf automake nano \
        python3-dev python3-pip python3-scipy python3-matplotlib \
        ipython3 python3-wxgtk4.0 python3-tk python3-igraph python3-pyx \
        libeigen3-dev libboost-all-dev libsuitesparse-dev \
        doxygen libopencv-dev libpoco-dev libtbb-dev libblas-dev liblapack-dev libv4l-dev \
        ros-noetic-cv-bridge ros-noetic-image-transport ros-noetic-image-proc ros-noetic-vision-opencv \
        python3-catkin-tools python3-osrf-pycommon \
    && rm -rf /var/lib/apt/lists/*

ARG KALIBR_REF=master
ARG BUILD_JOBS=2
WORKDIR /catkin_ws
RUN mkdir -p src && cd src && git clone --depth 1 -b ${KALIBR_REF} https://github.com/ethz-asl/kalibr.git
RUN . /opt/ros/noetic/setup.sh \
    && catkin init \
    && catkin config --extend /opt/ros/noetic \
    && catkin config --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && catkin build -j${BUILD_JOBS} \
    && chmod -R a+rX /catkin_ws

ENV MPLBACKEND=Agg
# igraph needs pycairo to draw the camera graph in the PDF report ("plotting not available")
RUN apt-get update && apt-get install -y --no-install-recommends python3-cairo && rm -rf /var/lib/apt/lists/*
# arm64: cv_bridge_boost fails to initialize unless cv2 is imported first
RUN echo "import cv2" >> /etc/python3.8/sitecustomize.py
ENV PATH=/catkin_ws/devel/lib/kalibr:$PATH
CMD ["bash"]
