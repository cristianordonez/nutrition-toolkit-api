FROM python:3.14


WORKDIR /code

#   - name: Install uv
#     uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b # v8.1.0
#   - name: Install Python 3.14
#     run: uv python install 3.14
#   - name: Build
#     run: uv build


COPY ./requirements.txt /code/requirements.txt


RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt


COPY ./app /code/app


CMD ["fastapi", "run", "app/main.py", "--port", "80"]