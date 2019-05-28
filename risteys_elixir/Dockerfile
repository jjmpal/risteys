# NOTE: assets (JS, CSS) MUST be handled locally beforehand:
# on your local machine, run:
#  npm prune
#  npm install
#  env NODE_ENV=production ./node_modules/webpack/bin/webpack.js --mode production
# this last one needs both NODE_ENV and --mode,
# see https://github.com/webpack/webpack/issues/7074.
#
# NOTE: Data import and DB migrations are NOT handled in this script,
# they must be done separately from a VM on Google Compute Engine
# beforehand.

FROM elixir

RUN mix local.hex --force
RUN mix local.rebar --force
RUN mix archive.install --force hex phx_new 1.4.3

ADD . /app
WORKDIR /app

RUN mix deps.get --only prod

ENV MIX_ENV prod

RUN mix compile
RUN mix phx.digest

ENTRYPOINT ["mix", "phx.server"]
