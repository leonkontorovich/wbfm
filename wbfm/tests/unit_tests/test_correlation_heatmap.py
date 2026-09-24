import unittest
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from wbfm.utils.visualization.utils_napari import (
    NapariPropertyHeatMapper,
    property_vector_to_colormap,
)


class TestCorrelationHeatmapColormap(unittest.TestCase):
    def test_property_vector_to_colormap_linear_scaling(self):
        """Verify correlation values in [-1, 1] map linearly without squaring."""
        vec_of_labels = [1, 2, 3, 4, 5]
        val_to_plot = [-1.0, -0.5, 0.0, 0.5, 1.0]

        prop_dict = property_vector_to_colormap(
            val_to_plot,
            vec_of_labels,
            scale_to_minus_1_and_1=True,
            cmap=plt.cm.RdBu
        )

        # In RdBu:
        # prop_scaled for -1.0 is 0.0 (red)
        # prop_scaled for 0.0 is 0.5 (white)
        # prop_scaled for 1.0 is 1.0 (blue)
        # prop_scaled for 0.5 is 0.75 (light blue, NOT 0.625 from squaring 0.25)
        np.testing.assert_allclose(prop_dict[1], plt.cm.RdBu(0.0), atol=1e-5)
        np.testing.assert_allclose(prop_dict[2], plt.cm.RdBu(0.25), atol=1e-5)
        np.testing.assert_allclose(prop_dict[3], plt.cm.RdBu(0.5), atol=1e-5)
        np.testing.assert_allclose(prop_dict[4], plt.cm.RdBu(0.75), atol=1e-5)
        np.testing.assert_allclose(prop_dict[5], plt.cm.RdBu(1.0), atol=1e-5)

        # Label 0 and None must be transparent
        np.testing.assert_allclose(prop_dict[0], np.array([0.0, 0.0, 0.0, 0.0]))
        np.testing.assert_allclose(prop_dict[None], np.array([0.0, 0.0, 0.0, 0.0]))

    def test_custom_val_to_plot_with_series(self):
        """Verify custom_val_to_plot handles pandas Series reindexing correctly."""
        names = ['neuron_001', 'neuron_002', 'neuron_003']
        cols = pd.MultiIndex.from_product([names, ['label', 'intensity_image', 'area']])
        df_red = pd.DataFrame(np.zeros((10, len(cols))), columns=cols)
        # Give each neuron a constant label ID: 10, 20, 30
        df_red.loc[:, ('neuron_001', 'label')] = 10
        df_red.loc[:, ('neuron_002', 'label')] = 20
        df_red.loc[:, ('neuron_003', 'label')] = 30

        heat_mapper = NapariPropertyHeatMapper(
            red_traces=df_red,
            green_traces=df_red,
            names=names
        )

        # Pass a series with a different order to verify reindexing
        val_to_plot = pd.Series([1.0, -1.0, 0.0], index=['neuron_003', 'neuron_001', 'neuron_002'])

        prop_dict = heat_mapper.custom_val_to_plot(val_to_plot, scale_to_minus_1_and_1=True)

        # neuron_001 is -1.0 -> label 10 should be RdBu(0.0) (Red)
        np.testing.assert_allclose(prop_dict[10], plt.cm.RdBu(0.0), atol=1e-5)
        # neuron_002 is 0.0 -> label 20 should be RdBu(0.5) (White)
        np.testing.assert_allclose(prop_dict[20], plt.cm.RdBu(0.5), atol=1e-5)
        # neuron_003 is 1.0 -> label 30 should be RdBu(1.0) (Blue)
        np.testing.assert_allclose(prop_dict[30], plt.cm.RdBu(1.0), atol=1e-5)


if __name__ == '__main__':
    unittest.main()
