function SANDIinput = dmri_preproc_sandi_batch_analysis(ProjectMainFolder, Delta, smalldelta, SNR, WithDot, Dsoma)
% Modified copy of SANDI_batch_analysis.m from
% https://github.com/palombom/SANDI-Matlab-Toolbox-Latest-Release
% (BSD 2-Clause License, Copyright (c) 2023, Marco Palombo - notice
% retained below per license terms).
%
% ONLY CHANGE: adds WithDot/Dsoma as explicit arguments and overrides
% SANDIinput.WithDot / SANDIinput.Dsoma with them after
% InitializeSANDIinput() runs. The upstream toolbox hardcodes
% SANDIinput.WithDot=0 and SANDIinput.Dsoma=3 inside
% functions/support_functions/InitializeSANDIinput.m with no way to
% override them from the caller otherwise - this is the smallest change
% that adds one. Everything else below is unmodified from upstream.
%
% --- original license notice ---
% BSD 2-Clause License
%
% Copyright (c) 2023, Marco Palombo
%
% Redistribution and use in source and binary forms, with or without
% modification, are permitted provided that the following conditions are met:
%
% 1. Redistributions of source code must retain the above copyright notice, this
%    list of conditions and the following disclaimer.
%
% 2. Redistributions in binary form must reproduce the above copyright notice,
%    this list of conditions and the following disclaimer in the documentation
%    and/or other materials provided with the distribution.
%
% THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
% AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
% IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
% DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
% FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
% DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
% SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
% CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
% OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
% OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
% --- end original license notice ---

addpath(genpath(fullfile(pwd, 'functions')));

%% Initialize analysis
SANDIinput = InitializeSANDIinput(ProjectMainFolder, Delta, smalldelta, SNR);

%%%% dMRI-preproc addition: override WithDot/Dsoma if provided %%%%
if nargin >= 5 && ~isempty(WithDot)
    SANDIinput.WithDot = WithDot;
end
if nargin >= 6 && ~isempty(Dsoma)
    SANDIinput.Dsoma = Dsoma;
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

disp('*****   SANDI analysis using Machine Learning based fitting method   ***** ')
dt = char(datetime("now"));
disp(['*****                          ' dt '                  ***** '])
fprintf(SANDIinput.LogFileID,'*****   SANDI analysis using Machine Learning based fitting method   ***** \n');
fprintf(SANDIinput.LogFileID,'*****                          %s                  ***** \n', dt);

%% STEP 1 - Preprocess the data: calculate the spherical mean signal and estimate noise distributions
SANDIinput = ProcessAllDatasets(SANDIinput); % Process all the datasets, one by one

%% STEP 2 - Train the Machine Learning (ML) model
SANDIinput = TrainMachineLearningModel(SANDIinput); % trains the ML model on synthetic data

% Saving the Training Set
Signals_train = SANDIinput.database_train_noisy;
Params_train = SANDIinput.params_train;
Performance_train = SANDIinput.train_perf;
Bvals_train = SANDIinput.model.bvals;
Sigma_mppca_train = SANDIinput.model.sigma_mppca;
Sigma_SHresiduals_train = SANDIinput.model.sigma_SHresiduals;

mkdir(fullfile(SANDIinput.StudyMainFolder, 'Report_ML_Training_Performance'));

save(fullfile(SANDIinput.StudyMainFolder, 'Report_ML_Training_Performance','TrainingSet.mat'), 'Signals_train',...
    'Params_train','Performance_train','Bvals_train', 'Sigma_mppca_train', 'Sigma_SHresiduals_train');

%% STEP 3 - SANDI fit each subject
SANDIinput = AnalyseAllDatasets(SANDIinput); % Analyse all the datasets, one by one

fclose(SANDIinput.LogFileID);
end
