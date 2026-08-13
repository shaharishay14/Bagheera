import os
import h5py
import torch
import shutil
import openslide
import numpy as np
import matplotlib.pyplot as plt
import umap  # Make sure it's installed
from glob import glob
from sklearn.manifold import TSNE
from tqdm import tqdm
from typing import Dict
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
import pandas as pd
import seaborn as sns

from prototype_visualization_utils import (
    get_panther_encoder,
    visualize_categorical_heatmap,
    get_default_cmap, get_mixture_plot
)
from mil_models.tokenizer import PrototypeTokenizer


VIS_LEVEL = 4
# GENERAL_OUT_DIR_NAME = 'Micromets_Camelyon16_panther_visualization'
GENERAL_OUT_DIR_NAME = 'Micromets_Camelyon16_Macro_Normal_Only'

class PrototypeVisualizer:
    def __init__(self, prototypes_n: int, base_dir: str, config_dir: str, prototype_pkl_template: str, vis_level: int = VIS_LEVEL):
        self.prototypes_n = prototypes_n
        self.base_dir = base_dir
        self.config_dir = config_dir
        self.prototype_path = prototype_pkl_template.format(n=prototypes_n)
        self.encoder = self.load_encoder()
        self.patch_size = None
        self.vis_level = vis_level
        # Paths
        self.slides_dir = os.path.join(base_dir, 'images')
        # self.h5_dir = os.path.join(base_dir, 'vasculitis_train_trident_processed/20x_256px_0px_overlap/feats_h5')
        self.h5_dir = os.path.join('../MicroMets/camelyon17_data', 'trident_processed/20x_256px_0px_overlap/feats_h5')
        # self.test_slides_dir = os.path.join(base_dir, 'vasculitis_test')
        self.test_slides_dir = os.path.join(base_dir, 'images')
        # self.test_h5_dir =  os.path.join(base_dir, 'vasculitis_test_trident_processed/20x_256px_0px_overlap/features_uni_v2')
        self.test_h5_dir =  os.path.join('../MicroMets/camelyon17_data', 'trident_processed/20x_256px_0px_overlap/feats_h5')
        # self.output_dir = os.path.join(f'{base_dir}/{GENERAL_OUT_DIR_NAME}', f'{prototypes_n}_prototypes')
        self.output_dir = os.path.join(f'src/visualization/Outputs/{GENERAL_OUT_DIR_NAME}', f'{prototypes_n}_prototypes')
        self.tsne_dir = os.path.join(self.output_dir, 'tsne')
        self.heatmap_dir = os.path.join(self.output_dir, 'panther_heatmaps')
        self.mixture_plot_dir = os.path.join(self.output_dir, 'mixture_plot')
        self.grouped_dir = os.path.join(self.output_dir, 'cluster_examples_grouped_prototypes')
        self.most_representative_patches = os.path.join(self.output_dir, 'most_representative_patches')
        self.GMM_dir = os.path.join(self.output_dir, 'GMM_features')

        os.makedirs(self.tsne_dir, exist_ok=True)
        os.makedirs(self.heatmap_dir, exist_ok=True)
        os.makedirs(self.mixture_plot_dir, exist_ok=True)
        os.makedirs(self.grouped_dir, exist_ok=True)
        os.makedirs(self.GMM_dir, exist_ok=True)

    def load_encoder(self):
        return get_panther_encoder(
            in_dim=1024,
            p=self.prototypes_n,
            proto_path=self.prototype_path,
            config_dir=self.config_dir
        )
    

    def Extract_GMM_Features(self):
        d_slide_cluster_labels: Dict[str, Dict[str, np.ndarray]] = dict()
        for filename in os.listdir(self.slides_dir):
            if not filename.endswith('.tif'):
                continue

            slide_path = os.path.join(self.slides_dir, filename)
            h5_path = os.path.join(self.h5_dir, filename.replace('.tif', '.h5'))

            if not os.path.exists(h5_path):
                print(f"Skipping {filename} (missing h5)")
                continue

            print(f"[→] Extracting GMM features for {filename}")
            wsi = openslide.open_slide(slide_path)
            h5 = h5py.File(h5_path, 'r')
            coords = h5['coords'][:]
            feats = torch.Tensor(h5['features'][:])

            with torch.inference_mode():
                info = self.encoder.representation(feats.unsqueeze(dim=0))

                qqs = info['qq']
                out = info['repr']
                tokenizer = PrototypeTokenizer(p=self.prototypes_n)
                pis, mus, sigmas = tokenizer.forward(out)
                print("Slide-specific mus:", mus)
                pis = pis[0].detach().cpu().numpy()
                qq = qqs[0, :, :, 0].cpu().numpy()
                cluster_labels = qq.argmax(axis=1)


                d_slide_cluster_labels[filename[:-len('.tif')]] = dict()
                d_slide_cluster_labels[filename[:-len('.tif')]]['mus'] = mus
                d_slide_cluster_labels[filename[:-len('.tif')]]['qq'] = qq
                d_slide_cluster_labels[filename[:-len('.tif')]]['pis'] = pis
                d_slide_cluster_labels[filename[:-len('.tif')]]['labels'] = cluster_labels
                d_slide_cluster_labels[filename[:-len('.tif')]]['repr'] = out

        np.save(os.path.join(self.GMM_dir , f"Prototypes_GMM_c{self.prototypes_n}_results.npy"),d_slide_cluster_labels)






    def generate_heatmaps(self):
        for filename in os.listdir(self.slides_dir):
            if not filename.endswith('.tif'):
                continue

            slide_path = os.path.join(self.slides_dir, filename)
            h5_path = os.path.join(self.h5_dir, filename.replace('.tif', '.h5'))

            if not os.path.exists(h5_path):
                print(f"Skipping {filename} (missing h5)")
                continue

            print(f"[→] Generating heatmap for {filename}")
            wsi = openslide.open_slide(slide_path)
            h5 = h5py.File(h5_path, 'r')
            coords = h5['coords'][:]
            feats = torch.Tensor(h5['features'][:])
            self.patch_size = h5['coords'].attrs['patch_size']

            with torch.inference_mode():
                info = self.encoder.representation(feats.unsqueeze(dim=0))
                qqs = info['qq']
                out = info['repr']
                tokenizer = PrototypeTokenizer(p=self.prototypes_n)
                pis, mus, sigmas = tokenizer.forward(out)
                pis = pis[0].detach().cpu().numpy()
                qq = qqs[0, :, :, 0].cpu().numpy()
                cluster_labels = qq.argmax(axis=1)

            ready_for_visualization_patch_size = self.patch_size * 2
            vis = visualize_categorical_heatmap(
                wsi,
                coords,
                cluster_labels,
                label2color_dict=get_default_cmap(self.prototypes_n),
                vis_level=self.vis_level,
                patch_size=(ready_for_visualization_patch_size, ready_for_visualization_patch_size),
                alpha=1
                #alpha=0.4
            )

            resized = vis.resize((vis.width // 4, vis.height // 4))
            heatmap_path = os.path.join(self.heatmap_dir, filename.replace('.tif', '_heatmap.jpg'))
            resized.save(heatmap_path)
            print(f"[✓] Heatmap saved: {heatmap_path}")

            mixture_plot_path = os.path.join(self.mixture_plot_dir, filename.replace('.tif', '_mixture_plot.jpg'))
            mixture_plot = get_mixture_plot(pis)
            mixture_plot.savefig(mixture_plot_path)
            plt.close(mixture_plot)
            print(f"[✓] Mixture plot saved: {mixture_plot_path}")

            # Save one example patch per cluster
            self.save_example_patches(wsi, coords, cluster_labels, filename)

    def save_example_patches(self, wsi, coords, cluster_labels, slide_filename):
        slide_name = slide_filename.replace('.tif', '')
        slide_output = os.path.join(self.heatmap_dir, slide_name)
        os.makedirs(slide_output, exist_ok=True)
        seen = set()

        for i, cluster in enumerate(cluster_labels):
            if cluster not in seen:
                seen.add(cluster)
                x, y = coords[i]
                patch = wsi.read_region((x, y), 0, (self.patch_size, self.patch_size)).convert('RGB')
                patch.save(os.path.join(slide_output, f'cluster_{cluster}.jpg'))
            if len(seen) == self.prototypes_n:
                break

    def organize_clusters(self):
        for slide_folder in os.listdir(self.heatmap_dir):
            slide_path = os.path.join(self.heatmap_dir, slide_folder)
            if not os.path.isdir(slide_path):
                continue

            for image_file in glob(os.path.join(slide_path, 'cluster_*.jpg')):
                cluster_id = int(os.path.basename(image_file).split('_')[1].split('.')[0])
                dest_dir = os.path.join(self.grouped_dir, f'cluster{cluster_id}')
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, f'{slide_folder}_{os.path.basename(image_file)}')
                shutil.copy(image_file, dest_path)
        print("[✔] Grouped patches by cluster.")

    def run_tsne_on_example_file(self, example_h5='../MicroMets/camelyon17_data/trident_processed/20x_256px_0px_overlap/feats_h5/tumor_020.h5'):
        with h5py.File(example_h5, 'r') as h5:
            feats = torch.Tensor(h5['features'][:])
            coords = h5['coords'][:]
            self.patch_size = h5['coords'].attrs['patch_size']

        with torch.inference_mode():
            info = self.encoder.representation(feats.unsqueeze(0))
            qq = info['qq'][0, :, :, 0].cpu().numpy()
            cluster_labels = qq.argmax(axis=1)
            out = info['repr']
            tokenizer = PrototypeTokenizer(p=self.prototypes_n)
            _, mus, _ = tokenizer.forward(out)
            mus = mus[0].cpu()
        dists = torch.cdist(feats, mus)
        closest_indices = dists.argmin(dim=0).cpu().numpy()

        example_h5_name = os.path.basename(example_h5)
        wsi_path = os.path.join(self.slides_dir, example_h5_name.replace('h5', 'tif'))
        wsi = openslide.open_slide(wsi_path)
        patch_dir = os.path.join(self.tsne_dir, f'closest_patches_{example_h5_name}')
        os.makedirs(patch_dir, exist_ok=True)

        for i, idx in enumerate(closest_indices):
            x, y = coords[idx]
            patch = wsi.read_region((x, y), 0, (self.patch_size, self.patch_size)).convert('RGB')
            patch.save(os.path.join(patch_dir, f'cluster_{i}.jpg'))

        tsne = TSNE(n_components=2, perplexity=30, random_state=42, init='pca')
        features_2d = tsne.fit_transform(feats.cpu().numpy())

        plt.figure(figsize=(10, 8))
        scatter = plt.scatter(features_2d[:, 0], features_2d[:, 1], c=cluster_labels, cmap='tab20', s=5)
        plt.colorbar(scatter, ticks=range(self.prototypes_n))
        plt.title('t-SNE Visualization of Patch Features')
        plt.tight_layout()
        plt.savefig(os.path.join(self.tsne_dir, f'tsne_{example_h5_name}_plot.png'))
        plt.close()
        print("[✓] t-SNE plot saved.")

    def _get_topk_patch_indices(self, feats, topk):
        """
        Returns indices of top-k patches closest to each prototype cluster center.
        """
        # Get the prototype vectors
        proto_array = np.load(self.prototype_path, allow_pickle=True)['prototypes'][0]  # (n_prototypes, 1536)
        prototypes = torch.tensor(proto_array, dtype=torch.float32)

        dists = torch.cdist(feats, prototypes)  # (N, P)
        sorted_indices = torch.argsort(dists, dim=0)  # (N, P)

        topk_indices_per_cluster = sorted_indices[:topk].cpu().numpy().T  # Shape: (P, K)
        return topk_indices_per_cluster  # list of K indices for each cluster

    def _collect_all_features(self):
        all_feats = []
        all_coords = []
        all_sources = []
        all_patch_sizes = []

        for h5_file in glob(os.path.join(self.h5_dir, '*.h5')):
            slide_id = os.path.basename(h5_file).replace('.h5', '')
            with h5py.File(h5_file, 'r') as h5:
                feats = torch.Tensor(h5['features'][:])
                coords = h5['coords'][:]
                patch_size = h5['coords'].attrs['patch_size']

                all_feats.append(feats)
                all_coords.append(coords)
                all_sources.extend([slide_id] * feats.shape[0])
                all_patch_sizes.append(patch_size)

        all_feats = torch.cat(all_feats, dim=0)
        all_coords = np.concatenate(all_coords, axis=0)
        self.patch_size = all_patch_sizes[0]  # assume consistent

        return all_feats, all_coords, all_sources

    def _extract_patches_by_indices(self, indices, all_coords, all_sources):
        patches = []
        for idx in indices:
            source_file = all_sources[idx]
            coord = all_coords[idx]
            slide_path = os.path.join(self.slides_dir, f'{source_file}.tif')

            if not os.path.exists(slide_path):
                patches.append(None)
                continue

            try:
                wsi = openslide.open_slide(slide_path)
                x, y = coord
                patch = wsi.read_region((x, y), 0, (self.patch_size, self.patch_size)).convert('RGB')
                patches.append(patch)
            except Exception as e:
                print(f"Error reading patch at ({x},{y}) in {slide_path}: {e}")
                patches.append(None)
        return patches

    def run_topk_visualization(self, topk=5):
        print(f"[📈] Running top-{topk} patch visualization for each prototype")

        feats, coords, sources = self._collect_all_features()
        topk_indices_per_cluster = self._get_topk_patch_indices(feats, topk)

        topk_patch_dir = os.path.join(self.most_representative_patches, f'top{topk}_patches')
        os.makedirs(topk_patch_dir, exist_ok=True)

        for cluster_id, topk_indices in enumerate(topk_indices_per_cluster):
            cluster_dir = os.path.join(topk_patch_dir, f'cluster_{cluster_id}')
            os.makedirs(cluster_dir, exist_ok=True)

            patches = self._extract_patches_by_indices(topk_indices, coords, sources)

            for rank, patch in enumerate(patches):
                if patch:
                    patch.save(os.path.join(cluster_dir, f'rank{rank}_{sources[topk_indices[rank]]}.jpg'))

        print(f"[✅] Saved top-{topk} patches per cluster in: {topk_patch_dir}")


    def run_topk_visualization_full_plot(self, topk=5):
        topk_patch_dir = os.path.join(self.most_representative_patches, f'top{topk}_patches_full_plot')
        os.makedirs(topk_patch_dir, exist_ok=True)

        proto_array = np.load(self.prototype_path, allow_pickle=True)['prototypes'][0]  # (n_prototypes, 1024)
        mus = torch.tensor(proto_array, dtype=torch.float32)

        dfs = list()

        for h5_file in tqdm(glob(os.path.join(self.h5_dir, '*.h5')),desc='Processing h5 files'):
            slide_id = os.path.basename(h5_file).replace('.h5', '')
            with h5py.File(h5_file, 'r') as h5:
                feats = torch.Tensor(h5['features'][:])


            dist_mat = euclidean_distances(feats, mus)
            temp_df = pd.DataFrame(dist_mat, columns=[f'proto_{i}' for i in range(self.prototypes_n)])
            temp_df['id'] = slide_id
            temp_df['slide_index'] = list(range(len(temp_df)))
            dfs.append(temp_df)


        df_dists = pd.concat(dfs, ignore_index=True)
        del dfs


        fig, ax = plt.subplots(topk, self.prototypes_n, figsize=(15,15))

        for p in range(self.prototypes_n):
            # gets the top closest tiles for each proto and plot them in the proto's colunm
            for row_idx, (idx, dist_val) in enumerate(df_dists['proto_'+str(p)].nsmallest(n=topk).items()):
                s_id = df_dists.at[idx, 'id']
                s_index = df_dists.at[idx, 'slide_index']
                
                s = openslide.open_slide(os.path.join(self.slides_dir, s_id + ".tif"))
                h5 = h5py.File(os.path.join(self.h5_dir, s_id+'.h5'), 'r')
                coords = h5['coords'][:]

                sampled_coords = coords[s_index]

                patch = s.read_region(location=sampled_coords, size=(512, 512), level=0).convert("RGB")
                
                ax[row_idx, p].imshow(patch)
                ax[row_idx, p].set_title(f"{p}\n{s_id} {sampled_coords}\ndist={dist_val:.3f}")
                ax[row_idx, p].axis('off')
                
        fig.tight_layout()
        plt.savefig(os.path.join(topk_patch_dir, f'All_prototypes_{topk}_patches.jpg'))

        print(f"[✅] Saved plot of top-{topk} patches for all clusters: {topk_patch_dir}")



    def run_topk_umap(self, topk=10):

        tsne_feats = []
        tsne_labels = []

        for filename in os.listdir(self.h5_dir):
            if not filename.endswith('.h5'):
                continue

            h5_path = os.path.join(self.h5_dir, filename)

            with h5py.File(h5_path, 'r') as h5:
                feats = torch.Tensor(h5['features'][:])

            slide_top_k_indices_per_cluster = self._get_topk_patch_indices(feats, topk)
            for cluster_id, indices in enumerate(slide_top_k_indices_per_cluster):
                for idx in indices:
                    tsne_feats.append(feats[idx].cpu().numpy())
                    tsne_labels.append(cluster_id)

        tsne_patch_dir = os.path.join(self.tsne_dir, f'umap_top{topk}_patches')
        os.makedirs(tsne_patch_dir, exist_ok=True)

        tsne_feats = np.array(tsne_feats)
        tsne_labels = np.array(tsne_labels)

        n_samples = len(tsne_feats)
        n_unique = len(np.unique(tsne_feats, axis=0))

        if n_unique < n_samples:
            print(f"[⚠️] Warning: {n_samples - n_unique} duplicate vectors found out of {n_samples} total samples.")

        print(f"[ℹ️] Running UMAP on {n_samples} samples, {n_unique} unique")

        reducer = umap.UMAP(n_components=2, random_state=42, metric="euclidean")
        features_2d = reducer.fit_transform(tsne_feats)

        plt.figure(figsize=(10, 8))
        scatter = plt.scatter(features_2d[:, 0], features_2d[:, 1], c=tsne_labels, cmap='tab20', s=5)
        plt.colorbar(scatter, ticks=range(self.prototypes_n))
        plt.title(f'UMAP of Top-{topk} Patches Per Prototype')
        plt.tight_layout()
        plt.savefig(os.path.join(tsne_patch_dir, 'umap_topk_plot.png'))
        plt.close()
        print(f"[✅] UMAP plot saved in {tsne_patch_dir}")

    def extract_cluster_patches(self, target_cluster, test=False):
        if not test:
            # do we actually need slides_dir here?
            slides_dir = self.slides_dir
            h5_dir = self.h5_dir
        else:
            slides_dir = self.test_slides_dir
            h5_dir = self.test_h5_dir

        out_prefix = "test_" if test else ""
        filtered_h5_dir = os.path.join(self.output_dir, f'{out_prefix}filtered_cluster{target_cluster}_h5')
        os.makedirs(filtered_h5_dir, exist_ok=True)

        for filename in os.listdir(slides_dir):
            if not filename.endswith('.tif'):
                continue

            h5_path = os.path.join(h5_dir, filename.replace('.tif', '.h5'))
            if not os.path.exists(h5_path):
                print(f"Skipping {filename} (missing h5)")
                continue

            print(f"[→] Extracting cluster {target_cluster} patches from {filename}")

            with h5py.File(h5_path, 'r') as h5:
                coords = h5['coords'][:]
                feats = torch.Tensor(h5['features'][:])
                patch_size = h5['coords'].attrs['patch_size']

            with torch.inference_mode():
                info = self.encoder.representation(feats.unsqueeze(0))  # (1, N, D)
                qq = info['qq'][0, :, :, 0].cpu().numpy()  # (N, C)
                cluster_labels = np.argmax(qq, axis=1)

            mask = cluster_labels == target_cluster
            filtered_feats = feats[mask].numpy()
            filtered_coords = coords[mask]

            print(f"  → Found {len(filtered_feats)} patches in cluster {target_cluster}")

            if len(filtered_feats) == 0:
                print(f"  → No patches found for cluster {target_cluster} in {filename}")
                continue

            # Save filtered h5
            out_h5_path = os.path.join(filtered_h5_dir, filename.replace('.tif', f'_cluster{target_cluster}.h5'))
            with h5py.File(out_h5_path, 'w') as out_h5:
                out_h5.create_dataset('features', data=filtered_feats)
                coords_ds = out_h5.create_dataset('coords', data=filtered_coords)
                coords_ds.attrs['patch_size'] = patch_size

            print(f"[✓] Saved filtered h5: {out_h5_path}")


    
    
    def _representative_coords(self, feats, mus, top_k):
        dist_mat = euclidean_distances(feats, mus)   # [num of tiles, num of protos]
        top_indices = dist_mat.argsort(axis=0)[:top_k]
        dist_mat.sort(axis=0) # can't find numpy sort not in-place
        return top_indices, dist_mat[:top_k]  # both of num_of_protos shape

    

    def run_topk_umap_from_dist_dataframe(self,topk=10):
        tsne_patch_dir = os.path.join(self.tsne_dir, f'umap_top{topk}_patches')
        os.makedirs(tsne_patch_dir, exist_ok=True)

        proto_array = np.load(self.prototype_path, allow_pickle=True)['prototypes'][0]  # n_prototypes, 1024
        mus = torch.tensor(proto_array, dtype=torch.float32)
        
        d_repr = np.load(os.path.join(self.GMM_dir , f"Prototypes_GMM_c{self.prototypes_n}_results.npy"), allow_pickle=True)[()]

        dfs = list()

        for h5_file in tqdm(glob(os.path.join(self.h5_dir, '*.h5')),desc='Processing h5 files'):
            slide_id = os.path.basename(h5_file).replace('.h5', '')
            with h5py.File(h5_file, 'r') as h5:
                feats = torch.Tensor(h5['features'][:])


            top_indices, top_dist_mat = self._representative_coords(feats, mus, topk)
            temp_df_dist = pd.DataFrame(top_dist_mat, columns=[f'proto_{i}' for i in range(mus.shape[0])])
            temp_df_indices = pd.DataFrame(top_indices, columns=[f'indices_{i}' for i in range(mus.shape[0])])
            temp_df_final = pd.concat([temp_df_dist, temp_df_indices], axis=1)
            temp_df_final['id'] = slide_id

            for i in range(mus.shape[0]):
                temp_df_final[f'feats_{i}'] = temp_df_final[f'indices_{i}'].apply(lambda i: feats[i])
                temp_df_final[f'labels_{i}'] = temp_df_final[f'indices_{i}'].apply(lambda i: d_repr[slide_id]['labels'][i])

            dfs.append(temp_df_final)


        df_feats_labels_all_slides = pd.concat(dfs, ignore_index=True)
        del dfs


        full_embeddings = []
        full_labels = []

        # Get all feat and label columns dynamically
        feat_cols = [c for c in df_feats_labels_all_slides.columns if c.startswith("feats_")]
        label_cols = [c for c in df_feats_labels_all_slides.columns if c.startswith("labels_")]

        for _, row in df_feats_labels_all_slides.iterrows():
            for fcol, lcol in zip(feat_cols, label_cols):
                feats = row[fcol]
                # Convert to numpy array (handle lists of tensors, tensors, or arrays)
                if isinstance(feats, list) and isinstance(feats[0], torch.Tensor):
                    feats = torch.stack(feats).numpy()
                elif isinstance(feats, torch.Tensor):
                    feats = feats.numpy()
                else:
                    feats = np.array(feats)

                full_embeddings.append(feats)
                full_labels.append(row[lcol])

        # Final arrays
        full_embeddings = np.vstack(full_embeddings)   # shape: (#rows * len(mu), feature_dim)
        full_labels = np.array(full_labels)   # shape: (#rows * len(mu),)

        print("full_embeddings:", full_embeddings.shape, "full_labels:", full_labels.shape)


        neighbors = 30
        reducer = umap.UMAP(n_neighbors=neighbors,random_state=42)
        umap_embeddings = reducer.fit_transform(full_embeddings)

        df_umap = pd.DataFrame(umap_embeddings)
        df_umap['labels'] = full_labels
        # df_umap['slide_id'] = full_slide_ids

        # Set the color palette
        # palette = sns.color_palette("tab10", n_colors=df['labels'].nunique())
        palette = get_default_cmap(n=mus.shape[0])
        palette = {k: tuple(v_i/255 for v_i in v) for k, v in palette.items()}
        palette = {str(k): v for k, v in palette.items()}
        
        # Create a new figure
        plt.figure(figsize=(8, 5))
        
        # Scatter plot
        sns.scatterplot(x=df_umap[0],y=df_umap[1],hue=df_umap['labels'].astype(str),palette=palette,s=10,edgecolor='none')
        
        # Titles and labels
        plt.title("UMAP Representative Tile Features")
        plt.xlabel("0")
        plt.ylabel("1")
        plt.legend(title="Labels", bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(os.path.join(tsne_patch_dir, 'umap_topk_plot_Dist_Indices_Dataframe.png'))

        print(f"[✅] Saved umap plot of top-{topk} patches for all clusters from datafrmae: {tsne_patch_dir}")

# === USAGE ===

if __name__ == '__main__':
    for k in range(17, 21, 1):
        print(f"starting create visualization for {k} prototypes")
    
        visualizer = PrototypeVisualizer(prototypes_n=k,
        base_dir='../../../../Data1/Data/external_datasets/CAMELYON16',
        config_dir='src/configs',
        # prototype_pkl_template='src/splits/camelyon16/prototypes/prototypes_c{n}_20x_256px_0px_overlap_kmeans_num_1.0e+05.pkl')
        prototype_pkl_template='src/splits/camelyon16_Macro_Normal_Only/prototypes/prototypes_c{n}_20x_256px_0px_overlap_kmeans_num_1.0e+05.pkl')

        visualizer.Extract_GMM_Features()
        visualizer.generate_heatmaps()
        visualizer.organize_clusters()
        # visualizer.run_tsne_on_example_file()
        visualizer.run_topk_visualization_full_plot()
        # visualizer.run_topk_visualization()
        # visualizer.run_topk_umap()
        visualizer.run_topk_umap_from_dist_dataframe()
