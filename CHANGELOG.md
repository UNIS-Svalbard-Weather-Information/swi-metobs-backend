# Changelog

## [3.3.1](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.3.0...3.3.1) (2026-10-14)


### Bug Fixes

* **spheres:** expose the Living Ice Project photographer as author ([dc3e2ca](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/dc3e2ca53cd1495480b6ce0fa1cb3962b03e4226))
* **spheres:** expose the Living Ice Project photographer as author ([8662f86](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/8662f86830d7ddf11b7285d3483304635ef02cfa))

## [3.3.0](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.2.2...3.3.0) (2026-10-14)


### Features

* **docker:** run the API as an unprivileged user ([1fae47a](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/1fae47a04f302f0442b6483f67f6e617959d3c67))
* **docker:** run the API as an unprivileged user ([dc00bfa](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/dc00bfafd7e66e77526f4da3f5031d0b1305fdd9))
* **spheres:** add Svalbox photospheres ([648dd80](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/648dd805ef2bc522d1d375faf60ea15b4c6efc56))
* **spheres:** add Svalbox photospheres as a provider ([56da3ee](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/56da3eeea05effb9e27b46a7ecb249117cd62aa3))
* **spheres:** load spheres in the background at startup ([07585e5](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/07585e533474cd523f94cee5be8d5e675a1f24c0))
* **spheres:** optional thumbnail, license and doi fields ([c19ded7](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/c19ded71463030147bca67743532b68981717f91))


### Bug Fixes

* **spheres:** treat a missing thumbnail as none in the LIP parser ([92182e9](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/92182e9a4c10e15ffd4d7d583ad86dbc9759c922))

## [3.2.2](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.2.1...3.2.2) (2026-10-11)


### Bug Fixes

* **deps:** refresh uv.lock to current releases ([23bf69c](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/23bf69c5d352e8adacc7a695965de654547a1ade))

## [3.2.1](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.2.0...3.2.1) (2026-10-11)


### Bug Fixes

* **observations:** return empty timeseries when the cache stores null ([#33](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/issues/33)) ([f8fa786](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/f8fa786c4b6c2188cb429e4abb36730d2e24eb4c))
* update dependencies ([7d853f9](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/7d853f9525ae7bc8f824c193bfaf995f2400c408))

## [3.2.0](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.1.0...3.2.0) (2026-10-04)


### Features

* point forecast time series endpoint ([#31](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/issues/31)) ([1432ef2](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/1432ef2300aa2500d00bae9008ed44e00ab742f5))

## [3.1.0](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.0.6...3.1.0) (2026-10-03)


### Features

* Add AROME-Arctic single-point forecast API with response caching ([479d367](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/479d367f1309ac5efc8e24a429674b872ffc81e2))

## [3.0.6](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.0.5...3.0.6) (2026-08-29)


### Bug Fixes

* publish images as a same-run job instead of a separate tag trigger ([2c53912](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/2c53912bbea0dd966fc8f91a48b716a362ace10f))

## [3.0.5](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/compare/3.0.4...3.0.5) (2026-08-29)


### Bug Fixes

* enable Docker healthcheck against the existing /health route ([037bb35](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/commit/037bb35440239924f85bdb567839cbcc13c7a7e5))
