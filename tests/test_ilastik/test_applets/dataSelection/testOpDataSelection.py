###############################################################################
#   ilastik: interactive learning and segmentation toolkit
#
#       Copyright (C) 2011-2014, the ilastik developers
#                                <team@ilastik.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# In addition, as a special exception, the copyright holders of
# ilastik give you permission to combine ilastik with applets,
# workflows and plugins which are not covered under the GNU
# General Public License.
#
# See the LICENSE file for details. License information is also available
# on the ilastik web site at:
#          http://ilastik.org/license.html
###############################################################################
import os
import shutil
from collections import defaultdict
import numpy
import vigra
import lazyflow
import h5py
from pathlib import Path
from PIL import Image

from lazyflow.utility.pathHelpers import PathComponents
from lazyflow.graph import Graph
from lazyflow.graph import OperatorWrapper
from ilastik.applets.dataSelection.opDataSelection import OpMultiLaneDataSelectionGroup, OpDataSelection
from ilastik.applets.dataSelection.opDataSelection import FilesystemDatasetInfo, ProjectInternalDatasetInfo
from ilastik.applets.dataSelection.dataSelectionSerializer import DataSelectionSerializer
from ilastik.applets.base.applet import DatasetConstraintError

import tempfile
import pytest

TOP_GROUP_NAME = "some_group"


@pytest.fixture
def serializer(empty_project_file, graph):
    opDataSelectionGroup = OpMultiLaneDataSelectionGroup(graph=graph)
    opDataSelectionGroup.ProjectFile.setValue(empty_project_file)
    opDataSelectionGroup.WorkingDirectory.setValue(Path(empty_project_file.filename).parent)
    opDataSelectionGroup.DatasetRoles.setValue(["Raw Data"])
    opDataSelectionGroup.DatasetGroup.resize(1)

    serializer = DataSelectionSerializer(opDataSelectionGroup, TOP_GROUP_NAME)
    return serializer


def save_to_hdf5(dataset_name, data, filename):
    with h5py.File(filename, "a") as f:
        f.create_dataset(name=dataset_name, data=data)


class TestOpDataSelection_Basic2D(object):
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.imgFileNames2D = []
        cls.imgFileNames2Dc = []
        cls.generatedImages2Dc = []
        # Comparison of compressed data not possible - those types will be
        # skipped in raw comparison:
        cls.compressedExtensions = [".jpg", ".jpeg"]
        cls.projectFileName = os.path.join(cls.tmpdir, "testProject.ilp")

        # Create a couple test images of different types
        # in order to simplify and unify testing among the different file types
        # the extra dimension is added, as vigra would add one anyway.
        cls.imgData2D = numpy.random.randint(0, 255, (10, 11, 1)).astype(numpy.uint8)
        # v- image data variables in order to reflect the correct axis-order
        # otherwise the axes get scrambled when writing/reloading
        vimgData2D = vigra.VigraArray(cls.imgData2D, axistags=vigra.defaultAxistags("yxc"), dtype=numpy.uint8)

        testNpyFileName = os.path.join(cls.tmpdir, "testimage2D.npy")
        numpy.save(testNpyFileName, cls.imgData2D)
        cls.imgFileNames2D.append(testNpyFileName)

        testNpzFileName = os.path.join(cls.tmpdir, "testimage2D.npz")
        numpy.savez(testNpzFileName, data=cls.imgData2D)
        testNpzFileName = "{}/data".format(testNpzFileName)
        cls.imgFileNames2D.append(testNpzFileName)

        testH5FileName = os.path.join(cls.tmpdir, "testimage2D.h5")

        save_to_hdf5(dataset_name="test/data", data=cls.imgData2D, filename=testH5FileName)
        testH5FileName = "{}/test/data".format(testH5FileName)
        cls.imgFileNames2D.append(testH5FileName)

        for extension in vigra.impex.listExtensions().split(" "):
            tmpFileName = os.path.join(cls.tmpdir, "testImage2D.{}".format(extension))
            # not all extensions support this kind of pixeltype
            try:
                vigra.impex.writeImage(vimgData2D, tmpFileName)
                cls.imgFileNames2D.append(tmpFileName)
            except RuntimeError as e:
                msg = str(e).replace("\n", "")
                print("Couldn't write temp 2D image file using vigra with `{}` extension : {}".format(extension, msg))

        cls.imgData2Dc = numpy.random.randint(0, 255, (100, 200, 3)).astype(numpy.uint8)
        vimgData2Dc = vigra.VigraArray(cls.imgData2Dc, axistags=vigra.defaultAxistags("yxc"), dtype=numpy.uint8)

        testNpyFileName = os.path.join(cls.tmpdir, "testimage2Dc.npy")
        numpy.save(testNpyFileName, cls.imgData2Dc)
        cls.imgFileNames2Dc.append(testNpyFileName)

        testNpzFileName = os.path.join(cls.tmpdir, "testimage2Dc.npz")
        numpy.savez(testNpzFileName, data=cls.imgData2Dc)
        testNpzFileName = "{}/data".format(testNpzFileName)
        cls.imgFileNames2Dc.append(testNpzFileName)

        testH5FileName = os.path.join(cls.tmpdir, "testimage2Dc.h5")
        save_to_hdf5(dataset_name="test/data", data=cls.imgData2Dc, filename=testH5FileName)
        testH5FileName = "{}/test/data".format(testH5FileName)
        cls.imgFileNames2Dc.append(testH5FileName)

        for extension in vigra.impex.listExtensions().split(" "):
            tmpFileName = os.path.join(cls.tmpdir, "testImage2Dc.{}".format(extension))
            # not all extensions support this kind of pixeltype
            try:
                vigra.impex.writeImage(vimgData2Dc, tmpFileName)
                cls.imgFileNames2Dc.append(tmpFileName)
                cls.generatedImages2Dc.append(tmpFileName)
            except RuntimeError as e:
                msg = str(e).replace("\n", "")
                print("Couldn't write temp 2D+c image file using vigra with `{}` extension : {}".format(extension, msg))

        # Create a 'project' file and give it some data
        cls.projectFile = h5py.File(cls.projectFileName, "w")
        cls.projectFile.create_group("DataSelection")
        cls.projectFile["DataSelection"].create_group("local_data")
        # Use the same data as the 2d+c data (above)
        cls.projectFile["DataSelection/local_data"].create_dataset("dataset1", data=cls.imgData2Dc)
        cls.projectFile.flush()

    @classmethod
    def teardown_class(cls):
        cls.projectFile.close()
        try:
            shutil.rmtree(cls.tmpdir)
        except OSError as e:
            print("Exception caught while deleting temporary files: {}".format(e))

    def create_nickname(self, fileName: str):
        comps = PathComponents(fileName)
        expected_nickname = Path(comps.externalPath).stem
        if comps.internalPath:
            expected_nickname += comps.internalPath.replace("/", "-")
        return expected_nickname

    def testBasic2D(self):
        """Test if plane 2d files are loaded correctly"""
        for fileName in self.imgFileNames2D:
            graph = lazyflow.graph.Graph()
            reader = OperatorWrapper(OpDataSelection, graph=graph, operator_kwargs={"forceAxisOrder": False})
            reader.ProjectFile.setValue(self.projectFile)
            reader.WorkingDirectory.setValue(os.getcwd())

            info = FilesystemDatasetInfo(filePath=fileName)

            reader.Dataset.setValues([info])

            # Read the test files using the data selection operator and verify the contents
            imgData2D = reader.Image[0][...].wait()

            assert reader.ImageName[0].value == self.create_nickname(fileName)
            # Check raw images
            assert imgData2D.shape == self.imgData2D.shape
            # skip this if image was saved compressed:
            if any(x in fileName.lower() for x in self.compressedExtensions):
                print("Skipping raw comparison for compressed data: {}".format(fileName))
                continue
            numpy.testing.assert_array_equal(imgData2D, self.imgData2D)

    def testBasic2Dc(self):
        """Test if 2d 3-channel files are loaded correctly"""
        # For some reason vigra saves 2D+c data compressed in gifs, so skip!
        self.compressedExtensions.append(".gif")
        for fileName in self.imgFileNames2Dc:
            graph = lazyflow.graph.Graph()
            reader = OperatorWrapper(OpDataSelection, graph=graph, operator_kwargs={"forceAxisOrder": False})
            reader.ProjectFile.setValue(self.projectFile)
            reader.WorkingDirectory.setValue(os.getcwd())

            info = FilesystemDatasetInfo(filePath=fileName)

            reader.Dataset.setValues([info])

            # Read the test files using the data selection operator and verify the contents
            imgData2Dc = reader.Image[0][...].wait()

            # Check the file name output
            assert reader.ImageName[0].value == self.create_nickname(fileName)
            # Check raw images
            assert imgData2Dc.shape == self.imgData2Dc.shape, (imgData2Dc.shape, self.imgData2Dc.shape)
            # skip this if image was saved compressed:
            if any(x in fileName.lower() for x in self.compressedExtensions):
                print("Skipping raw comparison for compressed data: {}".format(fileName))
                continue
            numpy.testing.assert_array_equal(imgData2Dc, self.imgData2Dc)

    def testProjectLocalData(self, serializer, empty_project_file, graph):
        for fileName in self.generatedImages2Dc:
            # For some reason vigra saves 2D+c data compressed in gifs, so skip!
            if Path(fileName).suffix in self.compressedExtensions + [".gif"]:
                continue
            filesystem_info = FilesystemDatasetInfo(filePath=fileName)

            # From project
            inner_path = filesystem_info.importAsLocalDataset(project_file=empty_project_file)
            info = ProjectInternalDatasetInfo(project_file=empty_project_file, inner_path=inner_path)

            projectInternalData = info.get_provider_slot(graph=graph)[...].wait()

            assert projectInternalData.shape == self.imgData2Dc.shape, (
                projectInternalData.shape,
                self.imgData2Dc.shape,
            )
            assert (projectInternalData == self.imgData2Dc).all()


class TestOpDataSelection_Basic_native_3D(object):
    """Test related to loading file types that support 3D"""

    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.imgFileNames3D = []
        cls.imgFileNames3DNicknames = []

        cls.imgFileNames3Dc = []
        cls.imgFileNames3DcNicknames = []

        cls.generatedImages3Dc = []
        # Comparison of compressed data not possible - those types will be
        # skipped in raw comparison:
        cls.projectFileName = os.path.join(cls.tmpdir, "testProject.ilp")

        # Create a couple test images of different types
        # in order to simplify and unify testing among the different file types
        # the extra dimension is added, as vigra would add one anyway.
        cls.imgData3D = numpy.random.randint(0, 255, (10, 11, 12, 1)).astype(numpy.uint8)
        # v- image data variables in order to reflect the correct axis-order
        # otherwise the axes get scrambled when writing/reloading
        vimgData3D = vigra.VigraArray(cls.imgData3D, axistags=vigra.defaultAxistags("zyxc"), dtype=numpy.uint8)

        testNpyFileName = os.path.join(cls.tmpdir, "testimage3D.npy")
        numpy.save(testNpyFileName, cls.imgData3D)
        cls.imgFileNames3D.append(testNpyFileName)
        cls.imgFileNames3DNicknames.append("testimage3D")

        testNpzFileName = os.path.join(cls.tmpdir, "testimage3D.npz")
        numpy.savez(testNpzFileName, data=cls.imgData3D)
        testNpzFileName = "{}/data".format(testNpzFileName)
        cls.imgFileNames3D.append(testNpzFileName)
        cls.imgFileNames3DNicknames.append("testimage3D-data")

        testH5FileName = os.path.join(cls.tmpdir, "testimage3D.h5")
        save_to_hdf5(dataset_name="test/data", data=cls.imgData3D, filename=testH5FileName)
        testH5FileName = "{}/test/data".format(testH5FileName)
        cls.imgFileNames3D.append(testH5FileName)
        cls.imgFileNames3DNicknames.append("testimage3D-test-data")

        cls.imgData3Dc = numpy.random.randint(0, 255, (10, 11, 12, 3)).astype(numpy.uint8)
        vimgData3Dc = vigra.VigraArray(cls.imgData3Dc, axistags=vigra.defaultAxistags("zyxc"), dtype=numpy.uint8)

        testNpyFileName = os.path.join(cls.tmpdir, "testimage3Dc.npy")
        numpy.save(testNpyFileName, cls.imgData3Dc)
        cls.imgFileNames3Dc.append(testNpyFileName)
        cls.imgFileNames3DcNicknames.append("testimage3Dc")
        cls.generatedImages3Dc.append(testNpyFileName)

        testNpzFileName = os.path.join(cls.tmpdir, "testimage3Dc.npz")
        numpy.savez(testNpzFileName, data=cls.imgData3Dc)
        testNpzFileName = "{}/data".format(testNpzFileName)
        cls.imgFileNames3Dc.append(testNpzFileName)
        cls.imgFileNames3DcNicknames.append("testimage3Dc-data")
        cls.generatedImages3Dc.append(testNpzFileName)

        testH5FileName = os.path.join(cls.tmpdir, "testimage3Dc.h5")
        save_to_hdf5(dataset_name="test/data", data=cls.imgData3Dc, filename=testH5FileName)
        testH5FileName = "{}/test/data".format(testH5FileName)
        cls.imgFileNames3Dc.append(testH5FileName)
        cls.imgFileNames3DcNicknames.append("testimage3Dc-test-data")
        cls.generatedImages3Dc.append(testH5FileName)

        # Create a 'project' file and give it some data
        cls.projectFile = h5py.File(cls.projectFileName, "w")
        cls.projectFile.create_group("DataSelection")
        cls.projectFile["DataSelection"].create_group("local_data")
        # Use the same data as the 3d+c data (above)
        cls.projectFile["DataSelection/local_data"].create_dataset("dataset1", data=cls.imgData3Dc)
        cls.projectFile.flush()

    @classmethod
    def teardown_class(cls):
        cls.projectFile.close()
        try:
            shutil.rmtree(cls.tmpdir)
        except OSError as e:
            print("Exception caught while deleting temporary files: {}".format(e))

    def testBasic3D(self):
        """Test if plane 2d files are loaded correctly"""
        for fileName, nickname in zip(self.imgFileNames3D, self.imgFileNames3DNicknames):
            graph = lazyflow.graph.Graph()
            reader = OperatorWrapper(OpDataSelection, graph=graph, operator_kwargs={"forceAxisOrder": False})
            reader.ProjectFile.setValue(self.projectFile)
            reader.WorkingDirectory.setValue(os.getcwd())
            reader.Dataset.setValues([FilesystemDatasetInfo(filePath=fileName)])

            # Read the test files using the data selection operator and verify the contents
            imgData3D = reader.Image[0][...].wait()

            # Check the file name output
            assert reader.ImageName[0].value == nickname
            # Check raw images
            assert imgData3D.shape == self.imgData3D.shape, (imgData3D.shape, self.imgData3D.shape)
            # skip this if image was saved compressed:
            numpy.testing.assert_array_equal(imgData3D, self.imgData3D)

    def testBasic3DWrongAxes(self):
        """Test if 3D file with intentionally wrong axes is rejected"""
        for fileName in self.imgFileNames3D:
            graph = lazyflow.graph.Graph()
            reader = OperatorWrapper(OpDataSelection, graph=graph, operator_kwargs={"forceAxisOrder": False})
            reader.ProjectFile.setValue(self.projectFile)
            reader.WorkingDirectory.setValue(os.getcwd())
            reader.ProjectDataGroup.setValue("DataSelection/local_data")

            info = FilesystemDatasetInfo(filePath=fileName, axistags=vigra.defaultAxistags("tzyc"))

            try:
                reader.Dataset.setValues([info])
                assert False, "Should have thrown an exception!"
            except DatasetConstraintError:
                pass
            except:
                assert False, "Should have thrown a DatasetConstraintError!"

    def testBasic3Dc(self):
        """Test if 2d 3-channel files are loaded correctly"""
        # For some reason vigra saves 2D+c data compressed in gifs, so skip!
        for fileName, nickname in zip(self.imgFileNames3Dc, self.imgFileNames3DcNicknames):
            graph = lazyflow.graph.Graph()
            reader = OperatorWrapper(OpDataSelection, graph=graph, operator_kwargs={"forceAxisOrder": False})
            reader.ProjectFile.setValue(self.projectFile)
            reader.WorkingDirectory.setValue(os.getcwd())
            reader.ProjectDataGroup.setValue("DataSelection/local_data")

            reader.Dataset.setValues([FilesystemDatasetInfo(filePath=fileName)])

            # Read the test files using the data selection operator and verify the contents
            imgData3Dc = reader.Image[0][...].wait()

            # Check the file name output
            assert reader.ImageName[0].value == nickname
            # Check raw images
            assert imgData3Dc.shape == self.imgData3Dc.shape, (imgData3Dc.shape, self.imgData3Dc.shape)
            # skip this if image was saved compressed:
            numpy.testing.assert_array_equal(imgData3Dc, self.imgData3Dc)

    def test3DProjectLocalData(self, serializer, empty_project_file, graph):
        empty_project_file.create_group("DataSelection")
        empty_project_file["DataSelection"].create_group("local_data")
        empty_project_file["DataSelection/local_data"].create_dataset("dataset1", data=self.imgData3Dc)
        info = ProjectInternalDatasetInfo(
            inner_path="DataSelection/local_data/dataset1", project_file=empty_project_file
        )

        projectInternalData = info.get_provider_slot(graph=graph)[...].wait()
        assert projectInternalData.shape == self.imgData3Dc.shape, (projectInternalData.shape, self.imgData3Dc.shape)
        assert (projectInternalData == self.imgData3Dc).all()

        for fileName in self.generatedImages3Dc:
            filesystem_info = FilesystemDatasetInfo(filePath=fileName)
            inner_path = filesystem_info.importAsLocalDataset(project_file=empty_project_file)
            info = ProjectInternalDatasetInfo(project_file=empty_project_file, inner_path=inner_path)

            projectInternalData = info.get_provider_slot(graph=graph)[...].wait()

            assert projectInternalData.shape == self.imgData3Dc.shape, (
                projectInternalData.shape,
                self.imgData3Dc.shape,
            )
            assert (projectInternalData == self.imgData3Dc).all()


class TestOpDataSelection_3DStacks(object):
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.imgFileNameGlobs2D = []
        cls.imgFileNameGlobs2DNicknames = []

        cls.imgFileNameGlobs2Dc = []
        cls.imgFileNameGlobs2DcNicknames = []

        cls.imgFileLists2D = defaultdict(list)

        cls.vigraExtensions = vigra.impex.listExtensions().split(" ")
        # Comparison of compressed data not possible - those types will be
        # skipped in raw comparison:
        cls.compressedExtensions = [".jpg", ".jpeg"]
        cls.projectFileName = os.path.join(cls.tmpdir, "testProject.ilp")

        # Create a couple test images of different types
        # in order to simplify and unify testing among the different file types
        # the extra dimension is added, as vigra would add one anyway.
        # 2D Stacks ##
        cls.imgData3D = numpy.random.randint(0, 255, (9, 10, 11, 1)).astype(numpy.uint8)
        # v- image data variables in order to reflect the correct axis-order
        # otherwise the axes get scrambled when writing/reloading
        cls.removedExtensions = []
        for slice_index, slice2D in enumerate(cls.imgData3D):
            vimgData2D = vigra.VigraArray(slice2D, axistags=vigra.defaultAxistags("yxc"), dtype=numpy.uint8)

            testNpyFileName = os.path.join(cls.tmpdir, "testimage2D_{:02d}.npy".format(slice_index))
            numpy.save(testNpyFileName, slice2D)

            testNpzFileName = os.path.join(cls.tmpdir, "testimage2D_{:02d}.npz".format(slice_index))
            numpy.savez(testNpzFileName, data=slice2D)
            testNpzFileName = "{}/data".format(testNpzFileName)

            testH5FileName = os.path.join(cls.tmpdir, "testimage2D_{:02d}.h5".format(slice_index))
            save_to_hdf5(dataset_name="test/data", data=slice2D, filename=testH5FileName)

            cls.imgFileLists2D["h5"].append("{}/test/data".format(testH5FileName))

            for extension in cls.vigraExtensions:
                if extension in cls.removedExtensions:
                    continue
                tmpFileName = os.path.join(cls.tmpdir, "testImage2D_{:02d}.{}".format(slice_index, extension))
                # not all extensions support this kind of pixeltype
                try:
                    vigra.impex.writeImage(vimgData2D, tmpFileName)
                    cls.imgFileLists2D[extension].append(tmpFileName)
                except RuntimeError as e:
                    cls.removedExtensions.append(extension)
                    msg = str(e).replace("\n", "")
                    print(
                        "Couldn't write temp 2D image file using vigra with `{}` "
                        "extension : {}".format(extension, msg)
                    )
        for extension in cls.removedExtensions:
            cls.vigraExtensions.pop(cls.vigraExtensions.index(extension))

        for extension in cls.vigraExtensions:
            cls.imgFileNameGlobs2D.append(os.path.join(cls.tmpdir, "testImage2D_*.{}".format(extension)))
            cls.imgFileNameGlobs2DNicknames.append("testImage2D_0")
        cls.imgFileNameGlobs2D.append(os.path.join(cls.tmpdir, "testimage2D_*.h5/test/data"))
        cls.imgFileNameGlobs2DNicknames.append("testimage2D_0-test-data")
        # uncomment once support is implemented
        # os.path.join(cls.tmpdir, "testimage2D_*.npz/data"),
        # os.path.join(cls.tmpdir, "testimage2D_*.npy"),

        # 2Dc Stacks ##
        cls.imgData3Dc = numpy.random.randint(0, 255, (9, 10, 11, 3)).astype(numpy.uint8)

        cls.removedExtensions = []
        for slice_index, slice2Dc in enumerate(cls.imgData3Dc):
            # v- image data variables in order to reflect the correct axis-order
            # otherwise the axes get scrambled when writing/reloading
            vimgData2Dc = vigra.VigraArray(slice2Dc, axistags=vigra.defaultAxistags("yxc"), dtype=numpy.uint8)

            testNpyFileName = os.path.join(cls.tmpdir, "testimage2Dc_{:02d}.npy".format(slice_index))
            numpy.save(testNpyFileName, slice2Dc)

            testNpzFileName = os.path.join(cls.tmpdir, "testimage2Dc_{:02d}.npz".format(slice_index))
            numpy.savez(testNpzFileName, data=slice2Dc)
            testNpzFileName = "{}/data".format(testNpzFileName)

            testH5FileName = os.path.join(cls.tmpdir, "testimage2Dc_{:02d}.h5".format(slice_index))
            save_to_hdf5(dataset_name="test/data", data=slice2Dc, filename=testH5FileName)

            for extension in cls.vigraExtensions:
                if extension in cls.removedExtensions:
                    continue
                tmpFileName = os.path.join(cls.tmpdir, "testImage2Dc_{:02d}.{}".format(slice_index, extension))
                # not all extensions support this kind of pixeltype
                try:
                    vigra.impex.writeImage(vimgData2Dc, tmpFileName)
                except RuntimeError as e:
                    cls.removedExtensions.append(extension)
                    msg = str(e).replace("\n", "")
                    print(
                        "Couldn't write temp 2D image file using vigra with `{}` "
                        "extension : {}".format(extension, msg)
                    )
        for extension in cls.removedExtensions:
            cls.vigraExtensions.pop(cls.vigraExtensions.index(extension))

        for extension in cls.vigraExtensions:
            cls.imgFileNameGlobs2Dc.append(os.path.join(cls.tmpdir, "testImage2Dc_*.{}".format(extension)))
            cls.imgFileNameGlobs2DcNicknames.append("testImage2Dc_0")

        cls.imgFileNameGlobs2Dc.append(os.path.join(cls.tmpdir, "testimage2Dc_*.h5/test/data"))
        cls.imgFileNameGlobs2DcNicknames.append("testimage2Dc_0-test-data")
        # uncomment once support is implemented
        # os.path.join(cls.tmpdir, "testimage2Dc_*.npz/data"),
        # os.path.join(cls.tmpdir, "testimage2Dc_*.npy"),

        # Create a 'project' file and give it some data
        cls.projectFile = h5py.File(cls.projectFileName, "w")
        cls.projectFile.create_group("DataSelection")
        cls.projectFile["DataSelection"].create_group("local_data")
        # Use the same data as the 3d+c data (above)
        cls.projectFile["DataSelection/local_data"].create_dataset("dataset1", data=cls.imgData3D)
        cls.projectFile.flush()

    @classmethod
    def teardown_class(cls):
        cls.projectFile.close()
        try:
            shutil.rmtree(cls.tmpdir)
        except OSError as e:
            print("Exception caught while deleting temporary files: {}".format(e))

    def testBasic3DstackFromGlobString(self, empty_project_file):
        """Test if stacked 2d files are loaded correctly"""

        reader = OperatorWrapper(OpDataSelection, graph=Graph(), operator_kwargs={"forceAxisOrder": False})
        reader.WorkingDirectory.setValue(str(Path(empty_project_file.filename).parent))
        for fileName, nickname in zip(self.imgFileNameGlobs2D, self.imgFileNameGlobs2DNicknames):
            reader.Dataset.setValues([FilesystemDatasetInfo(filePath=fileName, sequence_axis="z")])

            # Read the test files using the data selection operator and verify the contents
            imgData3D = reader.Image[0][...].wait()

            # Check the file name output
            assert reader.ImageName[0].value == nickname
            # Check raw images
            assert imgData3D.shape == self.imgData3D.shape, (imgData3D.shape, self.imgData3D.shape)
            # skip this if image was saved compressed:
            if any(x in fileName.lower() for x in self.compressedExtensions):
                print("Skipping raw comparison for compressed data: {}".format(fileName))
                continue
            numpy.testing.assert_array_equal(imgData3D, self.imgData3D)

    def testBasic3DstacksFromFileList(self, empty_project_file):
        for ext, fileNames in list(self.imgFileLists2D.items()):
            fileNameString = os.path.pathsep.join(fileNames)
            reader = OperatorWrapper(OpDataSelection, graph=Graph(), operator_kwargs={"forceAxisOrder": False})
            reader.WorkingDirectory.setValue(str(Path(empty_project_file.filename).parent))

            reader.Dataset.setValues([FilesystemDatasetInfo(filePath=fileNameString, sequence_axis="z")])

            # Read the test files using the data selection operator and verify the contents
            imgData3D = reader.Image[0][...].wait()

            # Check raw images
            assert imgData3D.shape == self.imgData3D.shape, (imgData3D.shape, self.imgData3D.shape)
            # skip this if image was saved compressed:
            if any(x.strip(".") in ext.lower() for x in self.compressedExtensions):
                print("Skipping raw comparison for compressed data: {}".format(ext))
                continue
            numpy.testing.assert_array_equal(imgData3D, self.imgData3D)

    def testBasic3DcStackFromGlobString(self, empty_project_file):
        """Test if stacked 2d 3-channel files are loaded correctly"""
        # For some reason vigra saves 2D+c data compressed in gifs, so skip!
        for fileName, nickname in zip(self.imgFileNameGlobs2Dc, self.imgFileNameGlobs2DcNicknames):
            reader = OperatorWrapper(OpDataSelection, graph=Graph(), operator_kwargs={"forceAxisOrder": False})
            reader.WorkingDirectory.setValue(str(Path(empty_project_file.filename).parent))

            reader.Dataset.setValues([FilesystemDatasetInfo(filePath=fileName, sequence_axis="z")])

            # Read the test files using the data selection operator and verify the contents
            imgData3Dc = reader.Image[0][...].wait()

            # Check the file name output
            assert reader.ImageName[0].value == nickname
            # Check raw images
            assert imgData3Dc.shape == self.imgData3Dc.shape, (imgData3Dc.shape, self.imgData3Dc.shape)
            # skip this if image was saved compressed:
            if any(x in fileName.lower() for x in self.compressedExtensions + [".gif"]):
                print("Skipping raw comparison for compressed data: {}".format(fileName))
                continue
            numpy.testing.assert_array_equal(imgData3Dc, self.imgData3Dc)


class TestOpDataSelection_SingleFileH5Stacks:
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.projectFileName = os.path.join(cls.tmpdir, "testProject.ilp")
        # generate some test data 'tczyx'
        cls.imgData3Dct = numpy.random.randint(0, 256, (10, 3, 8, 7, 6)).astype(numpy.uint8)

        # write a h5-file to directory
        cls.image_file_name = os.path.join(cls.tmpdir, "multi-h5.h5")

        h5file = h5py.File(cls.image_file_name, "w")
        cls.file_names = []
        try:
            g1 = h5file.create_group("g1")
            for t_index, t_slice in enumerate(cls.imgData3Dct):
                file_name = "timeslice_{:03d}".format(t_index)
                g1.create_dataset(file_name, data=t_slice)
                cls.file_names.append("{}/g1/{}".format(cls.image_file_name, file_name))
        finally:
            h5file.close()

        cls.glob_string = "{}/g1/timeslice_*".format(cls.image_file_name)
        # Create a 'project' file and give it some data
        cls.projectFile = h5py.File(cls.projectFileName, "w")
        cls.projectFile.create_group("DataSelection")
        cls.projectFile["DataSelection"].create_group("local_data")
        # Use the same data as the 3d+c data (above)
        cls.projectFile["DataSelection/local_data"].create_dataset("dataset1", data=cls.imgData3Dct)
        cls.projectFile.flush()

    @classmethod
    def teardown_class(cls):
        cls.projectFile.close()
        try:
            shutil.rmtree(cls.tmpdir)
        except OSError as e:
            print("Exception caught while deleting temporary files: {}".format(e))

    def test_load_single_file_with_glob(self):
        reader = OperatorWrapper(OpDataSelection, graph=Graph(), operator_kwargs={"forceAxisOrder": False})
        reader.WorkingDirectory.setValue(os.getcwd())

        reader.Dataset.setValues([FilesystemDatasetInfo(filePath=self.glob_string, sequence_axis="t")])

        # Read the test files using the data selection operator and verify the contents
        imgData = reader.Image[0][...].wait()

        # Check raw images
        assert imgData.shape == self.imgData3Dct.shape, (imgData.shape, self.imgData3Dct.shape)

        numpy.testing.assert_array_equal(imgData, self.imgData3Dct)

    def test_load_single_file_with_list(self):
        reader = OperatorWrapper(OpDataSelection, graph=Graph(), operator_kwargs={"forceAxisOrder": False})
        reader.WorkingDirectory.setValue(os.getcwd())

        fileNameString = os.path.pathsep.join(self.file_names)
        info = FilesystemDatasetInfo(filePath=fileNameString, sequence_axis="t")

        reader.Dataset.setValues([info])

        # Read the test files using the data selection operator and verify the contents
        imgData = reader.Image[0][...].wait()
        print("imgData", reader.Image.meta.axistags, reader.Image.meta.original_axistags)

        # Check raw images
        assert imgData.shape == self.imgData3Dct.shape, (imgData.shape, self.imgData3Dct.shape)

        numpy.testing.assert_array_equal(imgData, self.imgData3Dct)


class TestOpDataSelection_FileSeriesStacks:
    @pytest.fixture(scope="class")
    def tempdir(self, tmp_path_factory):
        temp_dir = tmp_path_factory.mktemp("test_stack_along_data")
        yield temp_dir
        shutil.rmtree(str(temp_dir))

    @pytest.fixture(scope="class")
    def series_data(self):
        R = [
            [1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        ]
        G = [
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
        ]
        B = [
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0],
        ]
        data = {
            "rgb00c": numpy.array(R, dtype=numpy.float32),  # b&w letters
            "rgb10c": numpy.array(G, dtype=numpy.float32),
            "rgb20c": numpy.array(B, dtype=numpy.float32),
        }
        data["rgb01c"] = data["rgb00c"][..., None]  # b&w letters with empty channel axis
        data["rgb11c"] = data["rgb10c"][..., None]
        data["rgb21c"] = data["rgb20c"][..., None]
        data["rgb03c"] = numpy.zeros((data["rgb00c"].shape[0], data["rgb00c"].shape[1], 3), dtype=numpy.float32)
        data["rgb13c"] = numpy.zeros((data["rgb10c"].shape[0], data["rgb10c"].shape[1], 3), dtype=numpy.float32)
        data["rgb23c"] = numpy.zeros((data["rgb20c"].shape[0], data["rgb20c"].shape[1], 3), dtype=numpy.float32)
        data["rgb03c"][..., 0] = data["rgb00c"]  # red R
        data["rgb13c"][..., 1] = data["rgb10c"]  # green G
        data["rgb23c"][..., 2] = data["rgb20c"]  # blue B
        return data

    @pytest.fixture(scope="class")
    def save_test_data(self, series_data, tempdir):
        base = tempdir
        for name, data in series_data.items():
            # save as h5
            save_to_hdf5(dataset_name="data", data=data, filename=base / f"{name}.h5")

            # save as png and tiff, if possible
            if name.endswith("0c"):
                im = Image.fromarray(data)
                im.save(base / f"{name}.tiff")
                vigra.impex.writeImage(image=(data.T * 255).astype(numpy.uint8), filename=str(base / f"{name}.png"))
            elif name.endswith("1c"):
                vigra.impex.writeImage(
                    image=(data.transpose(1, 0, 2) * 255).astype(numpy.uint8), filename=str(base / f"{name}.png")
                )
            elif name.endswith("3c"):
                data = (data * 255).astype(numpy.uint8)
                im = Image.fromarray(data, mode="RGB")
                im.save(base / f"{name}.tiff")
                vigra.impex.writeImage(image=data.transpose(1, 0, 2), filename=str(base / f"{name}.png"))

    @pytest.fixture(scope="class")
    def expected_data(self, series_data):
        series_0c = [series_data["rgb00c"], series_data["rgb10c"], series_data["rgb20c"]]
        series_3c = [series_data["rgb03c"], series_data["rgb13c"], series_data["rgb23c"]]
        return {
            "rgb0c_stack": numpy.stack(series_0c, axis=0),
            "rgb0c_stack_t": numpy.stack(series_0c, axis=2).transpose(1, 0, 2) * 255,
            "rgb0c_stack_2": numpy.stack(series_0c, axis=2),
            "rgb3c_concat": numpy.concatenate(series_3c, axis=2),
            "rgb3c_concat_t": numpy.concatenate(series_3c, axis=2).transpose(1, 0, 2) * 255,
            "rgb3c_concat_255": numpy.concatenate(series_3c, axis=2) * 255,
            "rgb0c_stack_None": numpy.stack(series_0c, axis=0)[..., None],
            "rgb0c_stack_None255": numpy.stack(series_0c, axis=0)[..., None] * 255,
            "rgb3c_stack": numpy.stack(series_3c, axis=0),
            "rgb3c_stack255": numpy.stack(series_3c, axis=0) * 255,
        }

    @pytest.mark.parametrize(
        "name, extension, sequence_axis, expected_key",
        [
            ["rgb*0c", ".h5/data", "c", "rgb0c_stack"],
            ["rgb*0c", ".png", "c", "rgb0c_stack_t"],
            ["rgb*0c", ".tiff", "c", "rgb0c_stack"],
            ["rgb*1c", ".h5/data", "c", "rgb0c_stack_2"],
            ["rgb*1c", ".png", "c", "rgb0c_stack_t"],
            ["rgb*3c", ".h5/data", "c", "rgb3c_concat"],
            ["rgb*3c", ".png", "c", "rgb3c_concat_t"],
            ["rgb*3c", ".tiff", "c", "rgb3c_concat_255"],
            ["rgb*0c", ".h5/data", "z", "rgb0c_stack_None"],
            ["rgb*0c", ".png", "z", "rgb0c_stack_None255"],
            ["rgb*0c", ".tiff", "z", "rgb0c_stack_None"],
            ["rgb*1c", ".h5/data", "z", "rgb0c_stack_None"],
            ["rgb*1c", ".png", "z", "rgb0c_stack_None255"],
            ["rgb*3c", ".h5/data", "z", "rgb3c_stack"],
            ["rgb*3c", ".png", "z", "rgb3c_stack255"],
            ["rgb*3c", ".tiff", "z", "rgb3c_stack255"],
            ["rgb*0c", ".h5/data", "t", "rgb0c_stack_None"],
            ["rgb*0c", ".png", "t", "rgb0c_stack_None255"],
            ["rgb*0c", ".tiff", "t", "rgb0c_stack_None"],
            ["rgb*1c", ".h5/data", "t", "rgb0c_stack_None"],
            ["rgb*1c", ".png", "t", "rgb0c_stack_None255"],
            ["rgb*3c", ".h5/data", "t", "rgb3c_stack"],
            ["rgb*3c", ".png", "t", "rgb3c_stack255"],
            ["rgb*3c", ".tiff", "t", "rgb3c_stack255"],
        ],
    )
    def test_stack_along(
        self, tempdir, save_test_data, expected_data, graph, name, extension, sequence_axis, expected_key
    ):
        fileName = tempdir / f"{name}{extension}"
        reader = OpDataSelection(graph=graph, forceAxisOrder=False)
        reader.WorkingDirectory.setValue(os.getcwd())
        reader.Dataset.setValue(FilesystemDatasetInfo(filePath=str(fileName), sequence_axis=sequence_axis))
        read = reader.Image[...].wait()
        expected = expected_data[expected_key]
        try:
            assert numpy.allclose(read, expected), f"{name}: {read.shape}, {expected.shape}"
        finally:
            reader.cleanUp()  # Ensure tempdir can be deleted


def test_cleanup(data_path, graph):
    filepath1 = data_path / "inputdata" / "2d3c.h5"  # Any file is fine
    filepath2 = data_path / "inputdata" / "3d.h5"
    reader = OpDataSelection(graph=graph)
    reader.WorkingDirectory.setValue(os.getcwd())

    # When
    reader.Dataset.setValue(FilesystemDatasetInfo(filePath=str(filepath1)))
    children_after_load = len(reader.children)
    reader.Dataset.setValue(FilesystemDatasetInfo(filePath=str(filepath2)))

    # Then
    assert len(reader.children) == children_after_load, "Did not clean up all children after input change"
