FROM python:3.11

# Ensure the output is not buffered
ENV PYTHONUNBUFFERED=1


# Copy the requirements file and install dependencies
COPY requirements.txt .

# Upgrade pip and setuptools, specifying versions for better compatibility
RUN pip install -U pip setuptools

# Install dependencies from requirements.txt
RUN pip install -r requirements.txt

# Install the package from GitHub
RUN pip install git+https://github.com/osuAkatsuki/akatsuki-cli

# Copy the scripts directory and ensure the scripts are executable
COPY scripts /scripts
RUN chmod u+x /scripts/*

# Copy the application code to the container
COPY . /srv/root
RUN chmod u+x /srv/root/*

# Set the working directory
WORKDIR /srv/root

# Expose port 80
EXPOSE 80

# Set the entry point for the container
ENTRYPOINT ["/scripts/run-bot.sh"]