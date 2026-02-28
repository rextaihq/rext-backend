import httpx
import json
import asyncio
from collections import defaultdict
from datetime import datetime

class StoreClient:
    def __init__(self, base_url: str = "http://127.0.0.1:2024"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def _flatten_namespace(self, ns_array):
        """Convert namespace array to string."""
        if isinstance(ns_array, list):
            return "".join(str(x) for x in ns_array)
        return str(ns_array)
    
    async def semantic_search_namespace(self, namespace: str, query: str, limit: int = 5):
        """Perform semantic search in a specific namespace."""
        response = await self.client.post(
            f"{self.base_url}/store/items/search",
            json={
                "namespace_prefix": [namespace],
                "limit": limit,
                "offset": 0,
                "query": query,
                "filter": None
            },
            timeout=30.0
        )
        
        data = response.json()
        items = []
        
        for item in data.get("items", []):
            ns_string = self._flatten_namespace(item["namespace"])
            if ns_string == namespace:
                items.append({
                    "key": item.get("key"),
                    "value": item.get("value"),
                    "score": item.get("score"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at")
                })
        
        return items
    
    async def semantic_search_all_namespaces(self, query: str, limit_per_ns: int = 5):
        """Perform semantic search across all namespaces."""
        response = await self.client.post(
            f"{self.base_url}/store/items/search",
            json={
                "namespace_prefix": [],
                "limit": 1000,
                "offset": 0,
                "query": query,
                "filter": None
            },
            timeout=30.0
        )
        
        data = response.json()
        namespaces_dict = defaultdict(list)
        
        for item in data.get("items", []):
            ns_string = self._flatten_namespace(item["namespace"])
            
            formatted_item = {
                "key": item.get("key"),
                "value": item.get("value"),
                "score": item.get("score"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at")
            }
            
            namespaces_dict[ns_string].append(formatted_item)
            
            # Limit results per namespace
            if len(namespaces_dict[ns_string]) >= limit_per_ns:
                break
        
        return dict(namespaces_dict)

    def _pretty_print_value(self, value, indent=0):
        """Pretty print a value with proper indentation."""
        prefix = "     " * indent
        
        if isinstance(value, dict):
            lines = []
            for key, val in value.items():
                if isinstance(val, (str, int, float, bool, type(None))):
                    lines.append(f"{prefix}  {key}: {val}")
                elif isinstance(val, list):
                    lines.append(f"{prefix}  {key}: [")
                    for idx, item in enumerate(val[:5]):  # Show first 5 items
                        if isinstance(item, (str, int, float, bool)):
                            lines.append(f"{prefix}    - {item}")
                        elif isinstance(item, dict):
                            lines.append(f"{prefix}    - {{...{len(item)} fields}}")
                    if len(val) > 5:
                        lines.append(f"{prefix}    ... +{len(val) - 5} more items")
                    lines.append(f"{prefix}  ]")
                elif isinstance(val, dict):
                    lines.append(f"{prefix}  {key}: {{")
                    for sub_key, sub_val in list(val.items())[:3]:
                        lines.append(f"{prefix}    {sub_key}: {sub_val}")
                    if len(val) > 3:
                        lines.append(f"{prefix}    ... +{len(val) - 3} more fields")
                    lines.append(f"{prefix}  }}")
            return "\n".join(lines)
        elif isinstance(value, list):
            lines = []
            for idx, item in enumerate(value[:5]):
                if isinstance(item, (str, int, float, bool)):
                    lines.append(f"{prefix}  - {item}")
                elif isinstance(item, dict):
                    lines.append(f"{prefix}  - {{...}}")
            if len(value) > 5:
                lines.append(f"{prefix}  ... +{len(value) - 5} more items")
            return "\n".join(lines)
        else:
            return f"{prefix}  {value}"

async def main():
    client = StoreClient()
    try:
        print("\n" + "=" * 120)
        print("🔍 LANGGRAPH STORE: SEMANTIC SEARCH WITH DETAILED RESULTS")
        print("=" * 120 + "\n")
        
        # Define search queries
        search_queries = [
            "LLM Rich",
        ]
        
        for search_query in search_queries:
            print("\n" + "-" * 120)
            print(f"🔎 Search Query: '{search_query}'")
            print("-" * 120 + "\n")
            
            # Perform semantic search
            search_results = await client.semantic_search_all_namespaces(
                query=search_query,
                limit_per_ns=5
            )
            
            if not search_results:
                print(f"❌ No matching items found for '{search_query}'\n")
                continue
            
            # Calculate total matches
            total_matches = sum(len(items) for items in search_results.values())
            print(f"✅ Found {total_matches} matching items across {len(search_results)} namespace(s)\n")
            
            # Display results by namespace
            for namespace_idx, namespace in enumerate(sorted(search_results.keys()), 1):
                items = search_results[namespace]
                
                print(f"\n📁 Namespace {namespace_idx}: {namespace}")
                print(f"   Matching items: {len(items)}\n")
                
                # Display each matching item with full details
                for item_idx, item in enumerate(items, 1):
                    key = item['key']
                    value = item['value']
                    score = item.get('score')
                    created_at = item.get('created_at')
                    updated_at = item.get('updated_at')
                    
                    # Similarity score visualization
                    if score is not None:
                        similarity = score * 100
                        score_bar = "█" * int(similarity / 5) + "░" * (20 - int(similarity / 5))
                        print(f"   [{item_idx}] Key: {key}")
                        print(f"       Similarity Score: {similarity:.2f}% [{score_bar}]")
                    else:
                        print(f"   [{item_idx}] Key: {key}")
                    
                    # Metadata
                    print(f"       Created: {created_at}")
                    print(f"       Updated: {updated_at}")
                    
                    # Full value content
                    print(f"\n       📦 Value Details:")
                    if isinstance(value, dict):
                        # Show all keys and their values
                        for key_name, val in value.items():
                            print(f"\n         {key_name}:")
                            
                            if isinstance(val, (str, int, float, bool, type(None))):
                                print(f"           {val}")
                            elif isinstance(val, list):
                                if all(isinstance(x, (str, int, float, bool)) for x in val):
                                    # Simple list
                                    for idx, item_val in enumerate(val[:10], 1):
                                        print(f"           {idx}. {item_val}")
                                    if len(val) > 10:
                                        print(f"           ... +{len(val) - 10} more items")
                                else:
                                    # Complex list
                                    print(f"           [{len(val)} items total]")
                                    for idx, item_val in enumerate(val[:3], 1):
                                        print(f"           {idx}. {item_val}")
                                    if len(val) > 3:
                                        print(f"           ... +{len(val) - 3} more items")
                            elif isinstance(val, dict):
                                # Nested dictionary
                                for sub_key, sub_val in val.items():
                                    print(f"           {sub_key}: {sub_val}")
                            else:
                                print(f"           {str(val)[:200]}...")
                    else:
                        print(f"           {value}")
                    
                    print()
            
            print("\n" + "=" * 120)

        # Additional: Show search statistics
        print("\n📊 Search Summary")
        print("=" * 120)
        print(f"Total queries performed: {len(search_queries)}")
        print(f"Store API Base URL: http://127.0.0.1:2024")
        print("=" * 120 + "\n")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.client.aclose()

if __name__ == "__main__":
    asyncio.run(main())