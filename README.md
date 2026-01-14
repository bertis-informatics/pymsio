# Pymsio

Pymsio is a small utility library for reading mass-spectrometry data files into a unified NumPy/Polars representation.  
Its Thermo RAW reader design was inspired by AlphaRaw, but implemented independently for the pymsio codebase.

It currently supports:

- **Thermo RAW** files (via `pythonnet` + Thermo Fisher CommonCore DLLs)
- **mzML** files

Both formats are exposed through a common interface.

---

## Requirements

- Python **>= 3.12**
- `pythonnet` is a **required dependency** (installed automatically with pymsio)
- For **Thermo RAW**, you must provide Thermo Fisher CommonCore DLLs (not redistributed)
- On Linux, Thermo RAW reading requires **Mono**. See the “Linux: install Mono” section below.

#### Recommended: download DLLs from RawFileReader GitHub (manual)

1. **Open the official RawFileReader repository**

   - In your browser, go to:  
     https://github.com/thermofisherlsms/RawFileReader

2. **Download the source as a ZIP file**

   - Click the green **“Code”** button.
   - Click **“Download ZIP”**.
   - Save the ZIP file (e.g. `RawFileReader-main.zip`) to a location you know.

3. **Extract the ZIP file**

   - Unzip `RawFileReader-main.zip`.
   - You should now have a folder like:

     ```text
     RawFileReader-main/
       Libs/
         Net471/
         NetCore/
           Net8/
           Net5/
         ...
     ```

4. **Locate the CommonCore DLLs**

   pymsio is currently tested with the **Net471** libraries.

   - Open the folder:

     ```text
     RawFileReader-main/Libs/Net471/
     ```

   - Inside that folder, find:

     - `ThermoFisher.CommonCore.Data.dll`
     - `ThermoFisher.CommonCore.RawFileReader.dll`

   (There may be additional DLLs in that folder; pymsio only needs the two above.)

   You will use these two files later in the installation steps,  
   so keep them in an easy-to-find location (e.g. on your Desktop or in a temporary `ThermoDLLs/` folder).<br><br>


#### Linux: install Mono (required for Thermo RAW)

To read Thermo `.raw` files with pymsio on Linux, **Mono is required** (pythonnet uses the Mono runtime by default on Linux/macOS).  

First, verify whether Mono is already installed:

```bash
mono --version
```

If Mono is **not** installed, install it using **the official Mono Project instructions**, or install it using the `install_mono.sh` script provided in the [pymsio GitHub repository](https://github.com/bertis-informatics/pymsio).<br><br>

---

## Installation

### Thermo RAW support setup

#### 1) Obtain Thermo Fisher CommonCore DLLs

pymsio needs the following .NET assemblies:

- `ThermoFisher.CommonCore.Data.dll`
- `ThermoFisher.CommonCore.RawFileReader.dll`

These DLLs are owned by Thermo Fisher Scientific and subject to their license, so **they are not bundled** with pymsio.<br><br>

#### 2) Install the DLLs where pymsio can find them

pymsio will look for the two DLLs in **either** of the following locations (in this order):

1) **A directory specified by an environment variable**  
2) **`<current working directory>/dlls/thermo_fisher/`** (i.e., relative to where you run)

#### Option 1) Environment variable-based DLL folder (recommended)

Set an environment variable to the folder that contains the two DLL files.

**Environment variable name**
- `PYMSIO_THERMO_DLL_DIR`

**Windows example**
1. Create a folder **(example)**:
   ```text
   C:\Users\{username}\Documents\pymsio\thermo_fisher
   ```
2. Copy these two files into it:
   - `ThermoFisher.CommonCore.Data.dll`
   - `ThermoFisher.CommonCore.RawFileReader.dll`
3. Set the env var (PowerShell):
   ```powershell
   setx PYMSIO_THERMO_DLL_DIR "C:\Users\{username}\Documents\pymsio\thermo_fisher"
   ```
4. Open a **new** terminal (so the env var is applied) and run your script.

**Linux example**
1. Create a folder **(example)**:
   ```text
   /home/{username}/dlls/thermo_fisher
   ```
2. Copy the two DLLs into that folder.
3. Set the env var (bash):
   ```bash
   export PYMSIO_THERMO_DLL_DIR="/home/{username}/dlls/thermo_fisher"
   ```
   (To persist it, add the export line to `~/.bashrc` or your shell profile.)

#### Option 2) CWD-based DLL folder (quick / portable)

If you prefer a project-local setup (no env vars), place the DLLs under:

```text
<your current working directory>/
  dlls/
    thermo_fisher/
      ThermoFisher.CommonCore.Data.dll
      ThermoFisher.CommonCore.RawFileReader.dll
```

For example, if you run Python from `/projects/my_run/`, then:

```text
/projects/my_run/dlls/thermo_fisher/
```  
 <br>

### Install pymsio

>If **conda (Anaconda or Miniconda)** is not installed, first **follow the [Install Miniconda (if needed)](#install-miniconda-if-needed) section** to install conda. Then, run the commands below.

```bash
conda create -n pymsio-env python=3.12 -y
conda activate pymsio-env
pip install -U pymsio
```

### Install Miniconda (if needed)

#### Windows

1. Open the official Miniconda / Anaconda download page:  
   https://www.anaconda.com/download
2. In the **Windows** section, download the **Miniconda (Windows 64-bit)** installer  
   (or Anaconda if you prefer the full distribution).
3. Run the downloaded `.exe` file.
4. Follow the installer steps.  
   If you are unsure about the options, you can generally accept the defaults.
5. After installation, open **Anaconda Prompt**.
6. Verify that Conda is available by running in Anaconda Prompt:

   ```powershell
   conda --version
   ```

   If this prints a version number, Conda is ready.

#### Linux

1. Open the official Miniconda / Anaconda download page:  
   https://www.anaconda.com/download
2. Download the **Miniconda (Linux x86_64)** installer  
   (file name similar to `Miniconda3-latest-Linux-x86_64.sh`).
3. In a terminal, go to the folder where the installer was downloaded and run:

   ```bash
   bash Miniconda3-latest-Linux-x86_64.sh
   ```

4. Follow the prompts:
   - Press **Enter** to scroll,
   - type `yes` to accept the license,
   - choose an install location (the default `~/miniconda3` is usually fine),
   - when asked to **initialize Conda**, answering **yes** is recommended.
5. Close the terminal and open a new one, then verify that Conda is available:

   ```bash
   conda --version
   ```

   If this prints a version number, Conda is ready.

---

## Quick Start

#### Read a file (Thermo RAW or mzML) via ReaderFactory

```python
from pathlib import Path
from pymsio.readers import ReaderFactory 

path = Path("path/to/your/file.raw")   # or .mzML

# 1) Get appropriate reader
reader = ReaderFactory.get_reader(path)

# 2) Read metadata (Polars DataFrame)
meta_df = reader.get_meta_df()
print(meta_df.head())

# 3) Read one frame (np.ndarray, shape (N, 2), [mz, intensity])
frame_num = int(meta_df.item(0, "frame_num"))
peaks = reader.get_frame(frame_num)
print(peaks.shape)

# 4) Load full dataset 
msdata = reader.load()
print(msdata.peak_arr.shape)
```

#### Read multiple frames

```python
frame_nums = meta_df["frame_num"].to_list() # or List[] which has frame numbers
peak_arr = reader.get_frames(frame_nums)
print(peak_arr.shape)
```

---

## Notes

- If Thermo RAW fails with missing assemblies, double-check that the two DLLs are in:
  `PYMSIO_THERMO_DLL_DIR` (Environment variable)
  or
  `.../{cwd}/dlls/thermo_fisher/`
