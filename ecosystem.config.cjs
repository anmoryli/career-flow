module.exports = {
  apps: [
    { name: 'careerflow-web', cwd: __dirname, script: '.venv/bin/gunicorn',
      args: '--bind 127.0.0.1:8000 --workers 2 --timeout 60 wsgi:app',
      interpreter: 'none', autorestart: true, max_restarts: 10, restart_delay: 3000,
      time: true, env: { APP_ENV: 'production' } },
    { name: 'careerflow-worker', cwd: __dirname, script: '.venv/bin/python',
      args: '-m app.worker', interpreter: 'none', autorestart: true,
      max_restarts: 10, restart_delay: 3000, time: true,
      env: { APP_ENV: 'production' } },
  ],
};
