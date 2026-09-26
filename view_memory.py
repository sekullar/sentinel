import chromadb

def main():
    # Chroma veritabanının olduğu klasörü gösteriyoruz
    client = chromadb.PersistentClient(path="./chroma_data")
    
    # Veritabanındaki koleksiyonları (tabloları) al
    collections = client.list_collections()
    
    if not collections:
        print("Chroma veritabanında hiçbir koleksiyon bulunamadı. Henüz bir şey kaydedilmemiş olabilir.")
        return

    for col in collections:
        print(f"\n{'='*50}")
        print(f"Koleksiyon (Tablo) Adı: {col.name}")
        print(f"{'='*50}")
        
        collection = client.get_collection(col.name)
        
        # Koleksiyondaki tüm verileri çek (limit belirtmezsek hepsini getirir)
        data = collection.get()
        
        ids = data.get('ids', [])
        documents = data.get('documents', [])
        metadatas = data.get('metadatas', [])
        
        if not ids:
            print("Koleksiyon var ama içi boş.")
            continue
            
        print(f"Toplam {len(ids)} kayıt bulundu:\n")
        
        for i in range(len(ids)):
            print(f"[{i+1}] ID : {ids[i]}")
            print(f"    Bilgi: {documents[i]}")
            # Eğer core/memory.py içinde metadata ekliyorsan (tarih, rol vb.) onlar da burada görünür
            if metadatas and metadatas[i]:
                print(f"    Meta : {metadatas[i]}")
            print("-" * 40)

if __name__ == "__main__":
    main()