# Short code to take in a cellcount Nifty (output of the stitch_cellpose function) and divide by the voxel size to create a cell density map.

# Author: Stephania Assimopoulos

#########

module load fsl/6.0.7.x

#########

input_img=$1

#########

# Get shape in each dimension

echo ""

echo "Robust value range of input image is: " 
fslstats $input_img -r

echo ""

#read -r nm1 val1 < <(fslinfo $input_img | grep "pixdim1")
#read -r nm2 val2 < <(fslinfo $input_img | grep "pixdim2")
#read -r nm3 val3 < <(fslinfo $input_img | grep "pixdim3")

val1=$(fslval "$input_img" pixdim1)
val2=$(fslval "$input_img" pixdim2)
val3=$(fslval "$input_img" pixdim3)

echo "Voxel size is: " $val1 " x " $val2 " x " $val3

# Create the factor to divide by

val=$(echo "$val1 * $val2 * $val3" | bc -l)
echo "Dividing by voxel volume: " $val

echo ""


# Divide to get the density

#output_img=${input_img//.nii/_density.nii}
output_img="${input_img%.nii.gz}_density.nii.gz"

fslmaths "$input_img" -div "$val" "$output_img"

echo "Robust value range of output image is: " 
fslstats $output_img -r

echo ""
echo "Density image saved in:"
echo $output_img

echo ""
echo "Done!"
echo ""
