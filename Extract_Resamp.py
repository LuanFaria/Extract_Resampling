import os
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping, Polygon
import geopandas as gpd
from pyproj import Transformer
import numpy as np
from rasterio.enums import Resampling
import pandas as pd

# INPUTS
raiz = "X:/Sigmagis/Projetos/COCAL/NDVI/2024/NOV/"
nome_base_ndvi = 'BASE_COCAL_NDVI_2025.shp'
#PASTA_NDVI = "X:/Sigmagis/Projetos/Grupo Clealco/NDVI/BERNARDO IDE/NDVI/"

img_=int(input('\n [1] - Sentinel\n [2] - Landsat\n'))
upscale_factor_sentinel = 4  #Divisor pxl, sentinel=4, LandSat=12
upscale_factor_land = 12


# PASTAS
BASE_NDVI = os.path.join(raiz, 'Vetores/Shape/', nome_base_ndvi)
PASTA_SHAPES = os.path.join(raiz, 'Vetores/shape/')
PASTA_IDADE = os.path.join(raiz, 'Vetores/shape/IDADE/')
PASTA_BUFFER = os.path.join(raiz, 'Vetores/shape/IDADE/BUFFER/')
PASTA_EXTRACT = os.path.join(raiz, 'Imagens/NDVI/EXTRACT/')
PASTA_RESAMPLE = os.path.join(raiz, 'Imagens/NDVI/RES/')
PASTA_NDVI = os.path.join(raiz, 'Imagens/NDVI/')


# Criando pastas (caso não exista)
print("Criando pastas no servidor...")
os.makedirs(os.path.join(PASTA_SHAPES, 'IDADE'), exist_ok=True)
os.makedirs(os.path.join(PASTA_IDADE, 'BUFFER'), exist_ok=True)
os.makedirs(os.path.join(PASTA_EXTRACT, 'TESTE'), exist_ok=True) 
os.makedirs(os.path.join(PASTA_NDVI, 'RES'), exist_ok=True) 
PASTA_EXT_TESTE =os.path.join(raiz, 'Imagens/NDVI/EXTRACT/TESTE/') 


# Exportando classes da base de talhões NDVI
print("Exportando Classes da base de talhoes NDVI...")
base_ndvi = gpd.read_file(BASE_NDVI)

import warnings
warnings.filterwarnings("ignore")  #IGNORA OS AVISOS DE ALERTASD

for classe in base_ndvi['CLASSE'].unique():
    print(classe)

    #Passo 2: SHAPE IDADE
    select_file = os.path.join(PASTA_IDADE, f'{classe}.shp')
    sub_df = base_ndvi[base_ndvi['CLASSE'] == classe]
    sub_df.to_file(select_file)
    print("Idade ok!")

    #Passo 3: BUFFER
    select_buf = os.path.join(PASTA_BUFFER, f'BUF_{classe}.shp')
    buf_gdf = sub_df.copy()
    #buf_gdf['geometry'] = buf_gdf.buffer(0.0005)  # Buffer de 50 metros
    buf_gdf['geometry'] = buf_gdf.buffer(50)  # Buffer de 50 metros
    
    dissolved_buf = buf_gdf.dissolve() #DISSOLVE - JUNTAR OS TALHÕES EM APENAS UM

    # Reatribuir a projeção após a dissolução
    dissolved_buf.crs = base_ndvi.crs
    dissolved_buf.to_file(select_buf)
    print("Buffer ok!")

    #Passo 4: EXTRACT BY MASK
    for imagem in dissolved_buf['OBS_IMG'].unique():
        select_ext = os.path.join(PASTA_EXTRACT, f'EXT_{classe}.tif')
        img_path = os.path.join(PASTA_NDVI, f'NDVI_{imagem}.tif')

        # Carregar shapefile como GeoDataFrame
        mask_gdf = gpd.read_file(select_buf)

        
        with rasterio.open(img_path) as src:
           
            raster_meta = src.meta.copy()
            
            if not src.crs:
                src.crs = mask_gdf.crs

            # Projeção do shapefile, se necessário
            mask_gdf = mask_gdf.to_crs(src.crs) if not mask_gdf.crs.equals(src.crs) else mask_gdf

            # Converter a geometria do GeoDataFrame para o formato adequado (formato GeoJSON)
            geoms = mask_gdf.geometry.apply(mapping)

            # Recortar o raster usando a geometria do shapefile como máscara
            out_image, out_transform = mask(src, geoms, crop=True)

            

            # Atualizar os metadados para o novo raster recortado
            out_meta = raster_meta.copy()
            out_meta.update({
                'height': out_image.shape[1],
                'width': out_image.shape[2],
                'transform': out_transform
                
            })

        
        with rasterio.open(select_ext, 'w', **out_meta) as dst:
            dst.write(out_image)
        
        print("Extract ok!")
        print(" ")
        #print(out_meta)
        #print(out_image)

# REMOVENDO FUNDO PRETO
if img_ == 1:
    print("REMOVENDO  MASCARA DE FUNDO...")
    for filename in os.listdir(PASTA_EXTRACT):
        if filename.endswith('.tif'):
            file = os.path.join(PASTA_EXTRACT, filename)
            output_file = os.path.join(PASTA_EXT_TESTE, f'{filename}')

            with rasterio.open(file) as src:
            # Ler o raster como um array numpy
                extract = src.read()
                
                
                # Definir o valor de fundo a ser removido
                # Neste caso, consideramos valores próximos de 0 como fundo preto
                background_value = 0
        
                # Verificar onde o fundo preto está presente
                fundo_preto = extract == background_value

                # Aplicar a máscara para manter apenas os pixels que não são de fundo
                ndvi_limpo = np.where(fundo_preto, np.nan, extract)  # Substituir o fundo preto por NaN

                # Atualizar os metadados para o novo raster recortado e limpo
                profile = src.profile
                profile.update({
                    'dtype': 'float32',  # Atualizar para o tipo de dados apropriado (float32 para suportar NaN)
                    'nodata': np.nan  # Definir NaN como valor nodata
                })

                # Salvar o raster recortado e limpo
                with rasterio.open(output_file, 'w', **profile) as dest:
                    dest.write(ndvi_limpo)

#Passo 5: RESAMPLE
    # GERANDO RESAMPLE
    print("GERANDO RESAMPLE SENTINEL")
    for filename in os.listdir(PASTA_EXT_TESTE): #ESSAS DUAS LINHAS
        if filename.endswith('.tif'):
            file = os.path.join(PASTA_EXT_TESTE, filename) #ESSA TBM
            output_file = os.path.join(PASTA_RESAMPLE, f'RES_{filename}')

            def resample_and_compress(file, output_file, upscale_factor, compression='LZW', dtype=rasterio.uint8, nodata=None):
                with rasterio.open(file) as dataset:
                    data = dataset.read(out_shape=(dataset.count, int(dataset.height * upscale_factor), int(dataset.width * upscale_factor)), resampling=Resampling.bilinear)

                    if nodata is not None:
                        data[data == np.nan] = nodata

                    transform = dataset.transform * dataset.transform.scale((dataset.width / data.shape[-1]), (dataset.height / data.shape[-2]))
                    profile.update({"height": data.shape[-2], "width": data.shape[-1], "transform": transform, "dtype": dtype, "compress": compression, "nodata": nodata})

                    with rasterio.open(output_file, 'w', **profile) as dst:
                        dst.write(data.astype(dtype))


            # Example usage with NoData value:
            #resample_and_compress(file, output_file, upscale_factor, compression='LZW', dtype=rasterio.uint8, nodata=255)

            # Example usage with float data type:
            resample_and_compress(file, output_file, upscale_factor_sentinel, compression='LZW', dtype=rasterio.float32, nodata=np.nan)

                
            
            print(f"Resample de {filename} finalizado!")

if img_ == 2:
    print("REMOVENDO  MASCARA DE FUNDO...")
    for filename in os.listdir(PASTA_EXTRACT):
        if filename.endswith('.tif'):
            file = os.path.join(PASTA_EXTRACT, filename)
            output_file = os.path.join(PASTA_EXT_TESTE, f'{filename}')

            with rasterio.open(file) as src:
            # Ler o raster como um array numpy
                extract = src.read()

                # Atualizar os metadados para o novo raster recortado e limpo
                profile = src.profile
                profile.update({
                    'dtype': 'float32',  # Atualizar para o tipo de dados apropriado (float32 para suportar NaN)
                  
                })

                # Salvar o raster recortado e limpo
                with rasterio.open(output_file, 'w', **profile) as dest:
                    dest.write(extract)
    # GERANDO RESAMPLE
    print("GERANDO RESAMPLE LANDSAT")
    for filename in os.listdir(PASTA_EXT_TESTE): #ESSAS DUAS LINHAS
        if filename.endswith('.tif'):
            file = os.path.join(PASTA_EXT_TESTE, filename) #ESSA TBM
            output_file = os.path.join(PASTA_RESAMPLE, f'RES_{filename}')

            def resample_and_compress(file, output_file, upscale_factor, compression='LZW', dtype=rasterio.uint8):
                with rasterio.open(file) as dataset:
                    data = dataset.read(out_shape=(dataset.count, int(dataset.height * upscale_factor), int(dataset.width * upscale_factor)), resampling=Resampling.bilinear)

                    transform = dataset.transform * dataset.transform.scale((dataset.width / data.shape[-1]), (dataset.height / data.shape[-2]))
                    profile.update({"height": data.shape[-2], "width": data.shape[-1], "transform": transform, "dtype": dtype, "compress": compression})

                    with rasterio.open(output_file, 'w', **profile) as dst:
                        dst.write(data.astype(dtype))


            # Example usage with NoData value:
            #resample_and_compress(file, output_file, upscale_factor, compression='LZW', dtype=rasterio.uint8, nodata=255)

            # Example usage with float data type:
            resample_and_compress(file, output_file, upscale_factor_land, compression='LZW', dtype=rasterio.float32)

                
            
            print(f"Resample de {filename} finalizado!")

print("RESAMPLE finalizado!!")
