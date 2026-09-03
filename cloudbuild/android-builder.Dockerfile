FROM ghcr.io/cirruslabs/android-sdk:35

ARG GRADLE_VERSION=8.11.1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        openjdk-17-jdk-headless \
        python3 \
        python3-pip \
        python3-venv \
    && wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle \
    && rm -f /tmp/gradle.zip \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN java -version \
    && python3 --version \
    && gradle --version \
    && sdkmanager --list_installed

