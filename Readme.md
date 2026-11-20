 Since the source version is working, we can build the final Windows .exe so you won't need PowerShell for normal use.

1. Close everything first
Close Laser Lab Control and the Micro Measurement Display/uMD GUI.


2. Open PowerShell in the project folder
You want to be here:

C:\Users\SS&AL\Desktop\NewLaserlab\laserai-4.1
You can enter:

cd "C:\Users\SS&AL\Desktop\NewLaserlab\laserai-4.1"

Then verify:

dir

You should see app.py, record_data.py, display.py, process_raw.py, etc.

3. Delete the OLD build
Run:

Remove-Item -Recurse -Force build

Then:

Remove-Item -Recurse -Force dist

If either says the folder doesn't exist, that's okay.

4. Build using your existing app.spec
You already have an app.spec in the project folder, so use:

pyinstaller --clean app.spec

Let it finish. Don't close PowerShell while it's building.

You want the end to say something similar to:

Building EXE completed successfully.
5. Find the new app
After it finishes:

cd dist
dir

You should see:

app.exe
Your project README confirms that the Windows build belongs under /dist/app.exe. 

Then launch it:

.\app.exe
