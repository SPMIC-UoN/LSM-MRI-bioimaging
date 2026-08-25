##########################
#############

# Wrapper script to run the tirl registration pipeline between to chosen images.
# Tailored for the LSM and MRI registration project.
# Author: Stephania Assimopoulos

##########################
#############

module load fsl/6.0.7.x
module load tirl

#############

YML_TEMPLATE=$1

SUBJECT=$2
REG=$3

OUTPUT_BASE_DIR=$4

SOURCE_FILE=$5
SOURCE_MASK_FILE=$6 # * Optional *

TARGET_FILE=$7
TARGET_MASK_FILE=$8 # * Optional *


#############

OUTPUT_DIR="$OUTPUT_BASE_DIR/$SUBJECT/$REG"

if [ ! -d $OUTPUT_DIR ]; then echo "output directory doesn't exist"; mkdir -p $OUTPUT_DIR; fi
if [ ! $OUTPUT_DIR ]; then echo "output directory exists"; fi

####

LOGFILE="$OUTPUT_DIR/logfile.log"
PARAM_LOGFILE="$OUTPUT_DIR/paramlog.log"

CONFIG="$OUTPUT_DIR/volume_to_volume.yml"


sed \
  -e "s|__OUTPUT_DIR__|${OUTPUT_DIR}|g" \
  -e "s|__LOGFILE__|${LOGFILE}|g" \
  -e "s|__PARAM_LOGFILE__|${PARAM_LOGFILE}|g" \
  -e "s|__SOURCE_FILE__|${SOURCE_FILE}|g" \
  -e "s|__SOURCE_MASK_FILE__|${SOURCE_MASK_FILE}|g" \
  -e "s|__TARGET_FILE__|${TARGET_FILE}|g" \
  -e "s|__TARGET_MASK_FILE__|${TARGET_MASK_FILE}|g" \
  $YML_TEMPLATE > "$CONFIG"


#############

tirl stanford.v2v --config "$CONFIG"

