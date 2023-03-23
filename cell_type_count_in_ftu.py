import os
import sys
from argparse import ArgumentParser
import glob

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.pyplot import figure
import seaborn as sns

from PIL import Image
import cv2
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

import json
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.pardir))
plt.rcParams['figure.figsize'] = (20, 20)
plt.style.use('ggplot')
sns.set_style("whitegrid", {'axes.grid': False})

CELL_X_BP_TEMPLATE = {
    "@context": "https://hubmapconsortium.github.io/ccf-ontology/ccf-context.jsonld",
    "@graph": [
        {
            "@id": None,
            "@type": "CellTypeSummary",
            "dataset": None,
            "summary": [

            ]
        }
    ]
}


def main():
    args = get_args()
    hnes = sorted(glob.glob(f"{args.hne_dir}/*.tif"))
    masks = sorted(glob.glob(f"{args.mask_dir}/*.tiff"))

    # load cells
    x = args.X
    y = args.Y
    cluster_col = args.cell_type
    cells = pd.read_csv(args.cell_csv_path)
    cells = pd.concat([cells, pd.get_dummies(cells[cluster_col])], 1)
    columns = ['Name']
    columns.extend(cells['Cell Type'].unique())
    cell_count_table = pd.DataFrame(columns=columns)
    mean_cell_count_table = pd.DataFrame(columns=columns)

    for hne_name, mask_name in zip(hnes, masks):
        hne = np.array(Image.open(mask_name.replace('masks', 'hne')[:-1]))
        mask = np.array(Image.open(mask_name))
        print(mask_name.replace('masks', 'hne')[:-1], mask_name)
        array, region, _, _ = mask_name.split('/')[-1].split('_')
        region = int(region[-1])
        # corresponding cells 
        mask_cells = cells[cells['array'] == array]
        mask_cells = mask_cells[mask_cells['region'] == region]

        height, width = mask.shape
        mask = cv2.resize(mask, (width * 2, height * 2), interpolation=cv2.INTER_AREA)

        cell_type_count = get_cell_type_count(mask, mask_cells)
        plot_cell_type_count(hne, cell_type_count, mask_cells,
                             f"{args.viz_dir}/{hne_name.split('/')[-1].replace('.tif', '.png')}")

        with open(f"{args.json_dir}/{hne_name.split('/')[-1].replace('.tif', '.json')}", "w") as outfile:
            json.dump(cell_type_count, outfile)

        # computed as sum(cell_type_counts in all ftu) / no_of_ftu
        mean_cell_type_counts = {}
        cell_type_counts = {}
        ftu_count = 0
        for index in cell_type_count.keys():
            ftu_count += 1
            for cell_type in cell_type_count[index]['cell_type_count'].keys():
                cell_type_counts.setdefault(cell_type, 0)
                cell_type_counts[cell_type] += cell_type_count[index]['cell_type_count'][cell_type]

        for cell_type in cell_type_counts.keys():
            mean_cell_type_counts[cell_type] = round(cell_type_counts[cell_type] / ftu_count)

        print(mean_cell_type_counts)

        cell_count = {'Name': hne_name.split('/')[-1][:-4]}
        cell_count.update(cell_type_counts)
        cell_count_table = cell_count_table.append(cell_count, ignore_index=True)

        mean_cell_count = {'Name': hne_name.split('/')[-1][:-4]}
        mean_cell_count.update(mean_cell_type_counts)
        mean_cell_count_table = mean_cell_count_table.append(mean_cell_count, ignore_index=True)

    cell_count_table.to_csv(args.out_dir + "cell_count.csv", index=False)
    mean_cell_count_table.to_csv(args.out_dir + "mean_cell_count.csv", index=False)


def plot_cell_type_count(hne, cell_type_count, mask_cells, out_dir):
    figure(figsize=(25, 25), dpi=40)
    cells = pd.DataFrame(columns=['X', 'Y', 'Cell Type'])
    width, height, _ = hne.shape
    hne = cv2.resize(hne, (height * 2, width * 2))
    for ftu_idx in cell_type_count.keys():
        ftu_contours = cell_type_count[ftu_idx]['ftu']
        cells = pd.concat([cells, pd.DataFrame(cell_type_count[ftu_idx]['cells'], columns=['X', 'Y', 'Cell Type'])])
        cv2.drawContours(image=hne, contours=np.array(ftu_contours), contourIdx=-1, color=(255, 0, 0), thickness=20,
                         lineType=cv2.LINE_AA)
    sns.scatterplot(cells, x='X', y='Y', hue='Cell Type', s=5)
    plt.imshow(hne)
    plt.legend(loc='best', prop={'size': 20})
    plt.savefig(out_dir)


def get_cell_type_count(mask, mask_cells):
    # height, width = mask.shape
    # mask = cv2.resize(mask, (width * 2, height * 2), interpolation=cv2.INTER_AREA)

    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    cell_type_count_in_ftu = {}
    for index, ftu_contour in enumerate(tqdm(contours)):
        try:
            ftu_polygon = Polygon(np.squeeze(ftu_contour))
        except ValueError as e:
            print(e)
            continue
        cell_type_count_in_ftu[index] = {
            'ftu': ftu_contour.tolist(),
            'cells': [],
            'cell_type_count': {}
        }
        for x, y, cell_type in zip(mask_cells['x'], mask_cells['y'], mask_cells['Cell Type']):
            point = Point(x, y)
            if ftu_polygon.contains(point):
                cell_type_count_in_ftu[index]['cells'].append([x, y, cell_type])
                cell_type_count_in_ftu[index]['cell_type_count'].setdefault(cell_type, 0)
                cell_type_count_in_ftu[index]['cell_type_count'][cell_type] += 1

    return cell_type_count_in_ftu


def get_args():
    parser = ArgumentParser()
    parser.add_argument("--hne_dir", default="./hne", type=str)
    parser.add_argument("--mask_dir", default="./masks", type=str)
    parser.add_argument("--viz_dir", default="./viz_low_res", type=str)
    parser.add_argument("--json_dir", default="./jsons", type=str)
    parser.add_argument("--out_dir", default="./", type=str)
    parser.add_argument("--cell_csv_path", default="/Users/abhiroop/Developer/cns/CODEX_HuBMAP_alldata_Dryad.csv", type=str)
    parser.add_argument("--X", default='X', type=str)
    parser.add_argument("--Y", default="Y", type=str)
    parser.add_argument("--cell_type", default="Cell Type", type=str)
    parser.add_argument("--region", default="unique_region", type=str)
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main()
