# Deploying

The service runs as a Knative Service on the z cluster (`yuisekin-z`, x86_64,
single node), in the `knative-pool` namespace alongside the other CNG proofs of
concept.

## Build and apply

The image is built on z and imported straight into containerd. There is no
registry in the loop, because the cluster is one node and the kubelet can see
what containerd holds. (The pi cluster cannot do this: its nodes each have
their own containerd, which is why `poc-cng-taroverture-openmaptiles` pushes to
`192.168.0.90:5000` instead.)

```sh
docker build -t ferspas-udf:0.1.4 .
docker save ferspas-udf:0.1.4 | ctr -n k8s.io images import -
kubectl apply -f k8s/z/namespace.yaml -f k8s/z/ksvc.yaml
kubectl get ksvc ferspas-udf -n knative-pool
curl -sI https://ferspas-udf.yuiseki.com/health
```

A bare image name is treated as `docker.io`, which `config-deployment` lists in
`registries-skipping-tag-resolving`, so Knative does not try to resolve a digest
for an image that was never pushed anywhere. Bump the tag on every rebuild:
`imagePullPolicy: IfNotPresent` against a reused tag will keep the old layers.

## Hostnames

Knative's domain on this cluster is `yuiseki.com`, and `*.yuiseki.com` already
resolves and already reaches Kourier through the tunnel, so applying the ksvc is
the whole job for <https://ferspas-udf.yuiseki.com>.

`yuiseki.net` is different. It has no wildcard; it carries individual records
(`stac`, `z`). So `ferspas-udf.yuiseki.net` needs three things, and only two of
them are in this repository.

**1. In the cluster (done by `k8s/z/domainmapping.yaml`).** A `DomainMapping`
makes Kourier answer for the name, and a `ClusterDomainClaim` grants the
namespace the right to take a name outside the cluster's own domain. Without
the claim the mapping reports `DomainAlreadyClaimed`, which reads like someone
else holds it rather than "nobody has granted it to you".

```sh
kubectl apply -f k8s/z/domainmapping.yaml
kubectl get domainmapping -n knative-pool          # expect READY=True
curl -sI -H 'Host: ferspas-udf.yuiseki.net' http://127.0.0.1:30880/health
```

**2. In Cloudflare (not doable from here; done for this service).** The tunnel
on this machine runs from a token, so its ingress rules live in the dashboard
rather than on disk:

- Zero Trust -> Networks -> Tunnels -> this tunnel -> Public Hostnames -> Add
- Hostname: `ferspas-udf.yuiseki.net`
- Service: `HTTP` -> `localhost:30880` (the Kourier NodePort)

Adding a public hostname creates the proxied DNS record as well. Point it at
the Kourier NodePort rather than at nginx: nginx on this host serves the static
`stac.yuiseki.net` and has no reason to sit in front of a Knative service.

If a subdomain per service becomes tedious, the alternative is a `*.yuiseki.net`
wildcard hostname on the tunnel pointing at `localhost:30880`, after which a
`DomainMapping` is the only per-service step. That is how `yuiseki.com` and
`yuiseki.dev` already behave.

**3. Nothing else.** Cloudflare's Universal SSL covers the apex and
first-level subdomains, and `ferspas-udf.yuiseki.net` is one level.

## Caching: only the tiles belong at the edge

A tile is expensive and immutable, so it carries
`Cache-Control: public, max-age=86400` and Cloudflare holds it. Everything else
carries `no-cache, must-revalidate`, and `/cache` and `/health` carry
`no-store` because a cached copy of a live number is a lie rather than a stale
page.

That split exists because of a specific trap. The pages originally sent no
`Cache-Control` at all, so Cloudflare applied its own TTL and held the viewer
HTML. Changing a page then meant purging, and purging the zone threw away the
tiles as well, which are the expensive half and take minutes of COG reads to
rebuild. Now a deploy is visible without purging anything: the page revalidates
and its ETag makes an unchanged one a 304.

If a purge is ever genuinely needed, purge by URL rather than everything.
Cloudflare's Custom Purge takes a list, so the pages can go without touching a
single tile:

```
https://ferspas-udf.yuiseki.net/
https://ferspas-udf.yuiseki.net/service.json
https://ferspas-udf.yuiseki.net/analysis
```

## After a deploy, the edge may hold the old answer

Cloudflare caches a 404. A request made before the hostname existed comes back
as `cf-cache-status: HIT` with the old 404 long after the origin is right, so a
failed check after a deploy means nothing until the cache is ruled out:

```sh
curl -sI "https://ferspas-udf.yuiseki.net/health?cb=$(date +%s)"
```

## Scaling notes

Startup is expensive: the lifespan hook builds an index per collection the
registry names, one DuckDB query against a 9.4 MB remote parquet apiece, about
30 s in total. The readiness probe is set to wait that out rather than
declaring the pod dead, and `scale-down-delay` is 600 s so a pod that has paid
for its index, its warm COG blocks and its tile cache is kept around.

The tile cache is `emptyDir`-backed under `/tmp` and capped at 256 MB per pod.
It is an optimisation: a pod that dies simply pays for its tiles again.

## What the cache looks like in the cluster

The tile cache is per pod, so its hit rate falls as the autoscaler adds pods
and goes to zero when it scales to zero. Measured on the live service with
three pods up: 14 tiles written, no hits, because consecutive requests landed
on different pods.

That is not worth fixing in the pod. Tiles carry
`Cache-Control: public, max-age=86400` and the edge is what makes it fast for
anyone else:

```
GET 1  4.66s  cf-cache-status: MISS
GET 2  0.39s  cf-cache-status: HIT
GET 3  0.08s  cf-cache-status: HIT
```

The on-disk cache still earns its place for the first visitor after a deploy
and for a pod being scrubbed through by one person, which is exactly the
scale-down-delay case it was sized for. A shared cache across pods would be a
volume or a Redis, and neither is worth it for a proof of concept.
