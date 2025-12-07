"""
Tests Celery + Redis - Démontre le traitement parallèle avec Celery.

Usage:
    pytest tests/test_celery.py -v -s
    pytest tests/test_celery.py -v -s -k "test_parallel"
    
Prérequis:
    - Redis running
    - Celery worker running: celery -A celery_app worker --loglevel=info
    - API running: uvicorn main_celery:app --port 8007
"""
import asyncio
import json
import time
import pytest
import httpx

# Configuration
API_URL = "http://localhost:8007"
TIMEOUT = 120.0


class TestHealthCheckCelery:
    """Tests de santé pour le mode Celery."""
    
    def test_health(self):
        """Vérifie que l'API répond."""
        response = httpx.get(f"{API_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data.get("backend") == "celery+redis", "Pas en mode Celery"
        print(f"\n✓ API OK (backend: {data.get('backend')})")
    
    def test_health_full(self):
        """Vérifie Redis et Celery workers."""
        response = httpx.get(f"{API_URL}/health/full", timeout=10)
        data = response.json()
        
        print(f"\n  Redis: {data.get('redis')}")
        print(f"  Celery: {data.get('celery_workers')}")
        print(f"  OpenAI: {data.get('openai')}")
        
        assert data["redis"] == "connected", "Redis non connecté"
        assert data["openai"] == "configured", "OpenAI non configuré"
        # Note: celery_workers peut être "no_workers" si pas de worker lancé


class TestCeleryAsync:
    """Tests du mode asynchrone Celery."""
    
    def test_chat_async_returns_task_id(self):
        """Vérifie que /chat/async retourne un task_id Celery."""
        start = time.time()
        
        response = httpx.post(
            f"{API_URL}/chat/async",
            json={"message": "Dis juste OK"},
            timeout=10
        )
        
        elapsed = time.time() - start
        
        assert response.status_code == 200
        data = response.json()
        
        # Vérifie la structure de réponse Celery
        assert data["status"] == "queued"
        assert "task_id" in data, "Manque task_id (spécifique Celery)"
        assert "session_id" in data
        assert "stream_url" in data
        
        # Doit retourner en moins de 1 seconde (fire-and-forget)
        assert elapsed < 1.0, f"Trop lent: {elapsed:.2f}s (devrait être < 1s)"
        
        print(f"\n✓ Réponse en {elapsed*1000:.0f}ms")
        print(f"  task_id: {data['task_id']}")
        print(f"  session_id: {data['session_id']}")
    
    def test_task_status_endpoint(self):
        """Vérifie l'endpoint de status des tâches Celery."""
        # Crée une tâche
        response = httpx.post(
            f"{API_URL}/chat/async",
            json={"message": "Test status"},
            timeout=10
        )
        data = response.json()
        task_id = data["task_id"]
        
        # Vérifie le status
        status_resp = httpx.get(f"{API_URL}/chat/{task_id}", timeout=10)
        status_data = status_resp.json()
        
        assert "status" in status_data
        assert status_data["task_id"] == task_id
        
        print(f"\n✓ Task status: {status_data['status']}")
    
    def test_priority_queues(self):
        """Vérifie que les priorités sont acceptées."""
        # Priorité haute
        resp_high = httpx.post(
            f"{API_URL}/chat/async",
            json={"message": "Urgent", "priority": 10},
            timeout=10
        )
        assert resp_high.status_code == 200
        
        # Priorité basse
        resp_low = httpx.post(
            f"{API_URL}/chat/async",
            json={"message": "Pas urgent", "priority": -10},
            timeout=10
        )
        assert resp_low.status_code == 200
        
        print("\n✓ Priorités high/low acceptées")


class TestCeleryStreaming:
    """Tests du streaming via Redis pub/sub."""
    
    @pytest.mark.asyncio
    async def test_stream_receives_chunks(self):
        """Vérifie que le stream SSE reçoit les chunks depuis Redis."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Envoie la requête
            resp = await client.post(
                f"{API_URL}/chat/async",
                json={"message": "Compte de 1 à 3"}
            )
            data = resp.json()
            session_id = data["session_id"]
            
            print(f"\n  Session: {session_id}")
            print(f"  Task: {data['task_id']}")
            
            # Écoute le stream
            chunks = []
            full_content = ""
            
            async with client.stream("GET", f"{API_URL}/stream/{session_id}") as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            event_data = json.loads(line[5:].strip())
                            chunks.append(event_data)
                            
                            # Celery envoie "content" pour les chunks
                            if "content" in event_data:
                                full_content += event_data["content"]
                                print(f"  chunk: {event_data['content'][:20]}...")
                            
                            # Fin du stream
                            if event_data.get("type") in ("complete", "error", "timeout"):
                                print(f"  → {event_data['type']}")
                                break
                        except json.JSONDecodeError:
                            pass
            
            assert len(chunks) >= 1, "Devrait recevoir au moins 1 event"
            print(f"\n✓ Reçu {len(chunks)} events, {len(full_content)} chars")


class TestCeleryParallel:
    """Tests de traitement parallèle avec Celery."""
    
    @pytest.mark.asyncio
    async def test_parallel_5_requests(self):
        """
        DÉMO: 5 requêtes envoyées simultanément via Celery.
        
        Celery distribue les tâches aux workers disponibles.
        """
        NUM_REQUESTS = 5
        messages = [f"Dis juste le chiffre {i}" for i in range(1, NUM_REQUESTS + 1)]
        
        print(f"\n{'='*50}")
        print(f"  TEST CELERY: {NUM_REQUESTS} requêtes en parallèle")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            start_total = time.time()
            
            async def send_and_wait(msg: str, index: int):
                start = time.time()
                
                # 1. Envoie (fire-and-forget)
                resp = await client.post(
                    f"{API_URL}/chat/async",
                    json={"message": msg}
                )
                data = resp.json()
                session_id = data["session_id"]
                task_id = data["task_id"]
                queue_time = time.time() - start
                
                # 2. Attend la réponse via SSE Redis
                result = ""
                async with client.stream("GET", f"{API_URL}/stream/{session_id}") as stream:
                    async for line in stream.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                event = json.loads(line[5:].strip())
                                if "content" in event:
                                    result += event["content"]
                                if event.get("type") in ("complete", "error", "timeout"):
                                    break
                            except:
                                pass
                
                elapsed = time.time() - start
                print(f"  Req #{index}: {elapsed:.2f}s | Queue: {queue_time*1000:.0f}ms | {result[:30]}...")
                return elapsed
            
            # Lance toutes les requêtes en parallèle
            tasks = [send_and_wait(msg, i+1) for i, msg in enumerate(messages)]
            times = await asyncio.gather(*tasks)
            
            total_time = time.time() - start_total
            avg_time = sum(times) / len(times)
            sequential_estimate = sum(times)
            
            print(f"\n{'='*50}")
            print(f"  RÉSULTATS CELERY")
            print(f"{'='*50}")
            print(f"  Temps total:        {total_time:.2f}s")
            print(f"  Temps moyen/req:    {avg_time:.2f}s")
            print(f"  Si séquentiel:      {sequential_estimate:.2f}s")
            print(f"  Gain parallélisme:  {sequential_estimate/total_time:.1f}x")
            print(f"{'='*50}")
            
            # Vérifie le parallélisme
            parallelism_ratio = sequential_estimate / total_time
            
            assert parallelism_ratio > 1.5, \
                f"Pas assez parallèle: ratio={parallelism_ratio:.1f}x"
            
            print(f"\n✓ Parallélisme Celery: {parallelism_ratio:.1f}x plus rapide!")


class TestCeleryRateLimiting:
    """Tests du rate limiting Celery."""
    
    @pytest.mark.asyncio
    async def test_burst_requests(self):
        """
        Test de burst: envoie plusieurs requêtes rapidement.
        Celery doit les absorber sans erreur.
        """
        NUM_REQUESTS = 10
        
        print(f"\n{'='*50}")
        print(f"  BURST TEST CELERY: {NUM_REQUESTS} requêtes")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            start = time.time()
            
            async def quick_send(i: int):
                resp = await client.post(
                    f"{API_URL}/chat/async",
                    json={"message": f"Burst test {i}"}
                )
                return resp.json()
            
            tasks = [quick_send(i) for i in range(NUM_REQUESTS)]
            results = await asyncio.gather(*tasks)
            
            queue_time = time.time() - start
            
            # Vérifie que toutes ont été acceptées
            task_ids = [r["task_id"] for r in results]
            session_ids = [r["session_id"] for r in results]
            
            print(f"  {NUM_REQUESTS} requêtes en queue en {queue_time*1000:.0f}ms")
            print(f"  Tasks créées: {len(task_ids)}")
            
            assert len(task_ids) == NUM_REQUESTS
            assert queue_time < 3.0, f"Trop lent: {queue_time:.2f}s"
            
            print(f"\n✓ Burst absorbé par Celery!")


class TestCeleryStats:
    """Tests des statistiques Celery."""
    
    @pytest.mark.asyncio
    async def test_stats_endpoint(self):
        """Vérifie l'endpoint de stats."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_URL}/stats")
            data = resp.json()
            
            assert "queues" in data
            assert "status" in data
            
            print(f"\n✓ Stats Celery:")
            print(f"  Queues: {data.get('queues')}")
            print(f"  Workers: {data.get('workers')}")
            print(f"  Active tasks: {data.get('active_tasks')}")


class TestCeleryVsSync:
    """Comparaison sync vs async."""
    
    @pytest.mark.asyncio
    async def test_compare_sync_vs_celery(self):
        """
        Compare le mode sync (/chat) vs Celery (/chat/async).
        """
        print(f"\n{'='*50}")
        print(f"  COMPARAISON: Sync vs Celery")
        print(f"{'='*50}")
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Test mode CELERY (fire-and-forget)
            start = time.time()
            resp = await client.post(
                f"{API_URL}/chat/async",
                json={"message": "Dis OK"}
            )
            celery_time = time.time() - start
            
            print(f"  Mode CELERY: {celery_time*1000:.0f}ms (retour immédiat)")
            assert celery_time < 0.5, "Mode Celery devrait retourner en < 500ms"
            
            # Test mode SYNC (attend la fin)
            start = time.time()
            resp = await client.post(
                f"{API_URL}/chat",
                json={"message": "Dis OK"}
            )
            content = resp.text
            sync_time = time.time() - start
            
            print(f"  Mode SYNC:  {sync_time:.2f}s (attend génération)")
            
            speedup = sync_time / celery_time
            print(f"\n  → Celery {speedup:.0f}x plus rapide pour libérer le serveur!")
            print(f"{'='*50}")


class TestEmbeddings:
    """Tests des embeddings batch."""
    
    def test_embeddings_endpoint(self):
        """Vérifie l'endpoint embeddings."""
        response = httpx.post(
            f"{API_URL}/embeddings",
            json={"texts": ["Hello", "World"]},
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "queued"
        assert "task_id" in data
        
        print(f"\n✓ Embeddings task créée: {data['task_id']}")


# Configuration pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
